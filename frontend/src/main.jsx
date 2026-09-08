import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

const statusText = { in_stock: '在库', checked_out: '借出', calibrating: '刻度中', inactive: '停用' }

async function api(path, options = {}) {
  const response = await fetch(`/api/v1${path}`, {
    credentials: 'include', ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
  })
  const text = await response.text()
  const body = text ? JSON.parse(text) : null
  if (!response.ok) throw new Error(body?.detail?.message || body?.error?.message || '请求失败')
  return body
}

function App() {
  const [user, setUser] = useState(null)
  const [page, setPage] = useState(window.location.pathname || '/')
  const [error, setError] = useState('')
  useEffect(() => {
    let mounted = true
    api('/auth/me').then(value => { if (mounted) setUser(value) }).catch(() => { if (mounted) setUser(false) })
    return () => { mounted = false }
  }, [])
  useEffect(() => {
    const onPopState = () => setPage(window.location.pathname || '/')
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])
  if (user === null) return <div className="loading">正在连接 JCSMS…</div>
  if (user === false) return <Login onLogin={setUser} onError={setError} error={error} />
  const navigate = (next) => { window.history.pushState({ path: next }, '', next); setPage(next); setError('') }
  return <ErrorBoundary><Shell user={user} page={page} navigate={navigate} onLogout={() => api('/auth/logout').then(() => setUser(false))} onLoginPage={() => setUser(false)} error={error} onError={setError} /></ErrorBoundary>
}

class ErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { error: null } }
  static getDerivedStateFromError(error) { return { error } }
  render() {
    if (this.state.error) return <main className="error-page"><h2>页面加载失败</h2><p>{this.state.error.message || '前端发生未知错误'}</p><button className="primary" onClick={() => window.location.reload()}>重新加载</button></main>
    return this.props.children
  }
}

function Login({ onLogin, onError, error }) {
  const [form, setForm] = useState({ username: '', password: '' })
  const submit = async (event) => {
    event.preventDefault()
    try { onLogin(await api('/auth/login', { method: 'POST', body: JSON.stringify(form) })) }
    catch (e) { onError(e.message) }
  }
  return <main className="login-page"><form className="login-card" onSubmit={submit}>
    <div className="eyebrow">JUNO · JCSMS V1</div><h1>放射源管理系统</h1><p>Calibration Source Registry</p>
    <label>用户名<input autoFocus value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} /></label>
    <label>密码<input type="password" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} /></label>
    {error && <div className="error">{error}</div>}<button className="primary">登录</button>
  </form></main>
}

function Shell({ user, page, navigate, onLogout, onLoginPage, error, onError }) {
  const is = (prefix) => page === prefix || page.startsWith(`${prefix}/`)
  const title = page === '/' ? '现场状态总览' : is('/sources') ? '放射源台账' : is('/calibrations') ? '刻度历史' : is('/audit') ? '审计日志' : is('/admin') ? '用户管理' : 'JCSMS'
  return <div className="app-shell"><aside>
    <div className="brand"><span>JCSMS</span><small>JUNO Calibration Sources</small></div>
    <nav><button className={page === '/' ? 'active' : ''} onClick={() => navigate('/')}>总览</button>
      <button className={is('/sources') ? 'active' : ''} onClick={() => navigate('/sources')}>放射源台账</button>
      <button className={is('/calibrations') ? 'active' : ''} onClick={() => navigate('/calibrations')}>刻度历史</button>
      {user.role === 'admin' && <button className={is('/audit') ? 'active' : ''} onClick={() => navigate('/audit')}>审计日志</button>}
      {user.role === 'admin' && <button className={is('/admin') ? 'active' : ''} onClick={() => navigate('/admin')}>用户管理</button>}
    </nav>
    <div className="side-foot">{user.guest ? <><span>访客 viewer</span><small>无需登录 · 只读</small><button onClick={onLoginPage}>管理登录</button></> : <><span>{user.username}</span><small>{user.role}</small><button onClick={onLogout}>退出登录</button></>}</div>
  </aside><main className="content"><header><div><div className="eyebrow">JUNO CALIBRATION SOURCE MANAGEMENT</div><h1>{title}</h1></div><div className="connection"><i />局域网运行</div></header>
    {error && <div className="error banner">{error}</div>}
    {page === '/' ? <Dashboard navigate={navigate} onError={onError} /> : is('/sources') ? <Sources page={page} navigate={navigate} user={user} onError={onError} /> : is('/calibrations') ? <Calibrations page={page} navigate={navigate} onError={onError} /> : is('/audit') && user.role === 'admin' ? <AuditPage onError={onError} /> : is('/admin') && user.role === 'admin' ? <AdminPage onError={onError} /> : <NotFound navigate={navigate} />}
  </main></div>
}

function Dashboard({ navigate, onError }) {
  const [data, setData] = useState(null)
  useEffect(() => { api('/dashboard').then(setData).catch(e => onError(e.message)) }, [onError])
  if (!data) return <div className="loading">加载总览…</div>
  return <><section className="metric-grid">{[['total', '管理中 Source'], ['in_stock', '在库'], ['checked_out', '借出'], ['calibrating', '刻度中']].map(([key, label]) => <div className="metric" key={key}><span>{label}</span><strong>{data.counts[key]}</strong><small>当前 Registry</small></div>)}</section>
    <section className="dashboard-grid"><Panel title="当前借出"><SourceMiniList items={data.checked_out} empty="没有借出的 Source" navigate={navigate} /></Panel><Panel title="当前刻度中"><SourceMiniList items={data.calibrating} empty="没有正在刻度的 Source" navigate={navigate} /></Panel></section>
    <Panel title="Recent Activity"><div className="activity-list">{data.recent_activity.length ? data.recent_activity.map(item => <div className="activity-row" key={item.id}><span className="dot" /><div><b>{item.action}</b><span>{item.source_id} · {item.operator || '系统'}</span></div><time>{formatDate(item.created_at)}</time></div>) : <Empty text="暂无操作记录" />}</div></Panel></>
}

function Sources({ page, navigate, user, onError }) {
  const id = page.startsWith('/sources/') ? decodeURIComponent(page.slice('/sources/'.length)) : null
  if (id === 'new') return <SourceForm navigate={navigate} onError={onError} />
  return id ? <SourceDetail id={id} user={user} navigate={navigate} onError={onError} /> : <SourceList navigate={navigate} onError={onError} user={user} />
}

function SourceForm({ navigate, onError }) {
  const [form, setForm] = useState({ display_name: '', isotope: 'Ge-68', serial_number: '', reference_value: '', reference_unit: 'Bq', reference_date: '', building: '', cabinet: '', position: '' })
  const update = (key, value) => setForm({ ...form, [key]: value })
  const submit = async (event) => {
    event.preventDefault()
    try {
      const body = { display_name: form.display_name, isotope: form.isotope, serial_number: form.serial_number, activity: { reference_value: Number(form.reference_value), reference_unit: form.reference_unit, reference_date: new Date(form.reference_date).toISOString() }, location: { building: form.building, cabinet: form.cabinet, position: form.position } }
      const created = await api('/sources', { method: 'POST', body: JSON.stringify(body) })
      navigate(`/sources/${encodeURIComponent(created.source_id)}`)
    } catch (e) { onError(e.message) }
  }
  return <form onSubmit={submit}><button type="button" className="back" onClick={() => navigate('/sources')}>← 返回台账</button><Panel title="新建放射源"><div className="form-grid"><label>显示名称<input required value={form.display_name} onChange={e => update('display_name', e.target.value)} /></label><label>核素<input required value={form.isotope} onChange={e => update('isotope', e.target.value)} /></label><label>序列号<input value={form.serial_number} onChange={e => update('serial_number', e.target.value)} /></label><label>参考数值<input required type="number" min="0.000001" value={form.reference_value} onChange={e => update('reference_value', e.target.value)} /></label><label>单位<select value={form.reference_unit} onChange={e => update('reference_unit', e.target.value)}><option value="Bq">Bq</option><option value="n/s">中子/秒</option></select></label><label>参考时间<input required type="datetime-local" value={form.reference_date} onChange={e => update('reference_date', e.target.value)} /></label><label>建筑<input value={form.building} onChange={e => update('building', e.target.value)} /></label><label>柜体<input value={form.cabinet} onChange={e => update('cabinet', e.target.value)} /></label><label>位置<input value={form.position} onChange={e => update('position', e.target.value)} /></label></div><button className="primary">创建 Source</button></Panel></form>
}

function SourceList({ navigate, onError, user }) {
  const [items, setItems] = useState([]); const [search, setSearch] = useState(''); const [isotope, setIsotope] = useState(''); const [location, setLocation] = useState(''); const [status, setStatus] = useState(''); const [inactive, setInactive] = useState(false)
  const load = () => api(`/sources?search=${encodeURIComponent(search)}&isotope=${encodeURIComponent(isotope)}&location=${encodeURIComponent(location)}&status=${status}&include_inactive=${inactive}`).then(setItems).catch(e => onError(e.message))
  useEffect(() => { load() }, [status, inactive])
  return <><div className="toolbar"><input placeholder="搜索 Source ID、名称、序列号" value={search} onChange={e => setSearch(e.target.value)} onKeyDown={e => e.key === 'Enter' && load()} /><input placeholder="核素" value={isotope} onChange={e => setIsotope(e.target.value)} onKeyDown={e => e.key === 'Enter' && load()} /><input placeholder="位置" value={location} onChange={e => setLocation(e.target.value)} onKeyDown={e => e.key === 'Enter' && load()} /><select value={status} onChange={e => setStatus(e.target.value)}><option value="">全部状态</option><option value="in_stock">在库</option><option value="checked_out">借出</option><option value="calibrating">刻度中</option><option value="inactive">停用</option></select><label className="checkbox"><input type="checkbox" checked={inactive} onChange={e => setInactive(e.target.checked)} />显示停用</label>{user.role === 'admin' && <button className="primary compact" onClick={() => navigate('/sources/new')}>新建 Source</button>}<button className="secondary compact" onClick={() => download('/sources/export.csv')}>导出 CSV</button></div>
    <Panel title={`${items.length} 个 Source`}><div className="table-wrap"><table><thead><tr><th>Source ID</th><th>名称</th><th>核素</th><th>当前活度</th><th>状态</th><th>位置 / 持有人</th><th>更新时间</th></tr></thead><tbody>{items.map(source => <tr key={source.source_id} onClick={() => navigate(`/sources/${encodeURIComponent(source.source_id)}`)}><td className="mono">{source.source_id}</td><td><b>{source.display_name}</b></td><td>{source.isotope}</td><td>{source.current_activity ? formatActivity(source.current_activity.activity) : '—'}</td><td><Status value={source.status} /></td><td>{source.current_holder || locationText(source.location) || '—'}</td><td>{formatDate(source.updated_at)}</td></tr>)}</tbody></table>{!items.length && <Empty text="没有符合条件的 Source" />}</div></Panel></>
}

function SourceDetail({ id, user, navigate, onError }) {
  const [data, setData] = useState(null); const [when, setWhen] = useState(''); const [activity, setActivity] = useState(null); const [busy, setBusy] = useState(false); const [editing, setEditing] = useState(false); const [modal, setModal] = useState(null)
  const load = () => api(`/sources/${encodeURIComponent(id)}`).then(setData).catch(e => onError(e.message))
  useEffect(() => { load() }, [id])
  if (!data) return <div className="loading">加载 Source…</div>
  const source = data.source
  const canOperate = user.role === 'operator' || user.role === 'admin'
  const stateActions = source.status === 'in_stock' ? <><button disabled={busy} onClick={() => setModal('checkout')}>借出</button><button disabled={busy} onClick={() => setModal('start')}>开始刻度</button></> : source.status === 'checked_out' ? <><button disabled={busy} onClick={() => setModal('return')}>归还</button><button disabled={busy} onClick={() => setModal('start')}>开始刻度</button></> : source.status === 'calibrating' ? <button disabled={busy} onClick={() => action('calibration/end')}>结束刻度</button> : null
  const action = async (path, body = {}) => { setBusy(true); try { await api(`/sources/${encodeURIComponent(id)}/${path}`, { method: 'POST', body: JSON.stringify(body) }); await load() } catch (e) { onError(e.message) } finally { setBusy(false) } }
  const submitAction = async body => { const path = modal === 'checkout' ? 'checkout' : modal === 'start' ? 'calibration/start' : 'return'; await action(path, body); setModal(null) }
  const calculate = async () => { try { setActivity(await api(`/sources/${encodeURIComponent(id)}/activity${when ? `?time=${encodeURIComponent(new Date(when).toISOString())}` : ''}`)) } catch (e) { onError(e.message) } }
  if (editing) return <SourceEdit source={source} onCancel={() => setEditing(false)} onSaved={async () => { setEditing(false); await load() }} onError={onError} />
  return <><button className="back" onClick={() => navigate('/sources')}>← 返回台账</button><div className="detail-head"><div><div className="eyebrow mono">{source.source_id}</div><h2>{source.display_name}</h2><p>{source.isotope} · {source.serial_number || '未填写序列号'}</p></div><Status value={source.status} /></div>
    <div className="action-row">{canOperate && stateActions}{user.role === 'admin' && <>{source.status === 'inactive' ? <button disabled={busy} onClick={() => action('reactivate')}>恢复</button> : <button disabled={busy} onClick={() => action('deactivate')}>停用</button>}<button className="secondary" onClick={() => setEditing(true)}>编辑</button></>}</div>
    <div className="detail-grid"><Panel title="基本信息"><Info label="Source ID" value={source.source_id} mono /><Info label="显示名称" value={source.display_name} /><Info label="核素" value={source.isotope} /><Info label="制造商" value={source.manufacturer || '—'} /><Info label="证书编号" value={source.certificate_number || '—'} /></Panel><Panel title="活度"><Info label="参考活度" value={formatActivity({ value: source.activity.reference_value, unit: source.activity.reference_unit })} /><Info label="参考时间" value={formatDate(source.activity.reference_date)} /><Info label="当前活度" value={data.current_activity ? formatActivity(data.current_activity.activity) : '—'} /><div className="calculator"><label>历史时刻<input type="datetime-local" value={when} onChange={e => setWhen(e.target.value)} /></label><button onClick={calculate}>计算活度</button>{activity && <strong>{formatActivity(activity.activity)} <small>{activity.warning ? '（含警告）' : ''}</small></strong>}</div></Panel><Panel title="状态与位置"><Info label="当前状态" value={statusText[source.status]} /><Info label="位置" value={locationText(source.location) || '—'} /><Info label="持有人" value={source.current_holder || '—'} /><Info label="状态开始" value={formatDate(source.status_since)} /></Panel></div>
    <div className="detail-grid lower"><Panel title="刻度历史"><CalibrationRows items={data.calibrations} navigate={navigate} /></Panel><Panel title="状态流转"><div className="activity-list">{data.transactions.map(item => <div className="activity-row" key={item.id}><span className="dot" /><div><b>{item.action}</b><span>{item.from_status || '—'} → {item.to_status || '—'} · {item.operator || '系统'}</span></div><time>{formatDate(item.created_at)}</time></div>)}</div></Panel></div>{modal && <ActionModal type={modal} username={user.username} onCancel={() => setModal(null)} onSubmit={submitAction} />}</>
}

function ActionModal({ type, username, onCancel, onSubmit }) {
  const [form, setForm] = useState(type === 'checkout' ? { holder: '', purpose: '', expected_return_at: '', comment: '' } : type === 'start' ? { calibration_system: '', operator: username, purpose: '', run_number: '', position_label: '', comment: '' } : { building: '', room: '', cabinet: '', position: '', comment: '' })
  const update = (key, value) => setForm({ ...form, [key]: value })
  const submit = event => { event.preventDefault(); if (type === 'checkout') onSubmit({ ...form, expected_return_at: form.expected_return_at ? new Date(form.expected_return_at).toISOString() : null }); else if (type === 'start') onSubmit(form); else onSubmit({ location: { building: form.building, room: form.room, cabinet: form.cabinet, position: form.position }, comment: form.comment }) }
  const title = type === 'checkout' ? '借出 Source' : type === 'start' ? '开始刻度' : '归还 Source'
  return <div className="modal-backdrop"><form className="modal-card" onSubmit={submit}><h3>{title}</h3>{type === 'checkout' && <><label>持有人 *<input required value={form.holder} onChange={e => update('holder', e.target.value)} /></label><label>用途 *<input required value={form.purpose} onChange={e => update('purpose', e.target.value)} /></label><label>预计归还<input type="datetime-local" value={form.expected_return_at} onChange={e => update('expected_return_at', e.target.value)} /></label><label>备注<textarea value={form.comment} onChange={e => update('comment', e.target.value)} /></label></>}{type === 'start' && <><label>刻度系统 *<input required value={form.calibration_system} onChange={e => update('calibration_system', e.target.value)} /></label><label>操作人 *<input required value={form.operator} onChange={e => update('operator', e.target.value)} /></label><label>用途 *<input required value={form.purpose} onChange={e => update('purpose', e.target.value)} /></label><label>Run Number<input value={form.run_number} onChange={e => update('run_number', e.target.value)} /></label><label>Position<input value={form.position_label} onChange={e => update('position_label', e.target.value)} /></label><label>备注<textarea value={form.comment} onChange={e => update('comment', e.target.value)} /></label></>}{type === 'return' && <><label>建筑<input value={form.building} onChange={e => update('building', e.target.value)} /></label><label>房间<input value={form.room} onChange={e => update('room', e.target.value)} /></label><label>柜体<input value={form.cabinet} onChange={e => update('cabinet', e.target.value)} /></label><label>位置<input value={form.position} onChange={e => update('position', e.target.value)} /></label><label>备注<textarea value={form.comment} onChange={e => update('comment', e.target.value)} /></label></>}<div className="modal-actions"><button type="button" className="secondary" onClick={onCancel}>取消</button><button className="primary">确认</button></div></form></div>
}

function SourceEdit({ source, onCancel, onSaved, onError }) {
  const [form, setForm] = useState({ display_name: source.display_name, isotope: source.isotope, serial_number: source.serial_number, reference_value: source.activity.reference_value, reference_unit: source.activity.reference_unit, reference_date: source.activity.reference_date.slice(0, 16), building: source.location.building, room: source.location.room, cabinet: source.location.cabinet, position: source.location.position, manufacturer: source.manufacturer, certificate_number: source.certificate_number, notes: source.notes })
  const update = (key, value) => setForm({ ...form, [key]: value })
  const submit = async event => { event.preventDefault(); try { await api(`/sources/${encodeURIComponent(source.source_id)}`, { method: 'PATCH', body: JSON.stringify({ display_name: form.display_name, isotope: form.isotope, serial_number: form.serial_number, activity: { reference_value: Number(form.reference_value), reference_unit: form.reference_unit, reference_date: new Date(form.reference_date).toISOString(), uncertainty_fraction: source.activity.uncertainty_fraction }, location: { building: form.building, room: form.room, cabinet: form.cabinet, position: form.position }, manufacturer: form.manufacturer, certificate_number: form.certificate_number, notes: form.notes }) }); await onSaved() } catch (e) { onError(e.message) } }
  return <form onSubmit={submit}><button type="button" className="back" onClick={onCancel}>← 返回 Source</button><Panel title={`编辑 ${source.source_id}`}><div className="form-grid"><label>显示名称<input required value={form.display_name} onChange={e => update('display_name', e.target.value)} /></label><label>核素<input required value={form.isotope} onChange={e => update('isotope', e.target.value)} /></label><label>序列号<input value={form.serial_number} onChange={e => update('serial_number', e.target.value)} /></label><label>参考数值<input required type="number" min="0.000001" value={form.reference_value} onChange={e => update('reference_value', e.target.value)} /></label><label>单位<select value={form.reference_unit} onChange={e => update('reference_unit', e.target.value)}><option value="Bq">Bq</option><option value="n/s">中子/秒</option></select></label><label>参考时间<input required type="datetime-local" value={form.reference_date} onChange={e => update('reference_date', e.target.value)} /></label><label>制造商<input value={form.manufacturer} onChange={e => update('manufacturer', e.target.value)} /></label><label>证书编号<input value={form.certificate_number} onChange={e => update('certificate_number', e.target.value)} /></label><label>建筑<input value={form.building} onChange={e => update('building', e.target.value)} /></label><label>房间<input value={form.room} onChange={e => update('room', e.target.value)} /></label><label>柜体<input value={form.cabinet} onChange={e => update('cabinet', e.target.value)} /></label><label>位置<input value={form.position} onChange={e => update('position', e.target.value)} /></label><label>备注<input value={form.notes} onChange={e => update('notes', e.target.value)} /></label></div><button className="primary">保存修改</button></Panel></form>
}

function Calibrations({ page, navigate, onError }) { const id = page.startsWith('/calibrations/') ? page.slice('/calibrations/'.length) : null; return id ? <CalibrationDetail id={id} navigate={navigate} onError={onError} /> : <CalibrationList navigate={navigate} onError={onError} /> }
function CalibrationList({ navigate, onError }) {
  const [items, setItems] = useState([]); const [search, setSearch] = useState(''); const [source, setSource] = useState(''); const [isotope, setIsotope] = useState(''); const [system, setSystem] = useState(''); const [run, setRun] = useState(''); const [operator, setOperator] = useState(''); const [from, setFrom] = useState(''); const [to, setTo] = useState('')
  const load = () => { const query = new URLSearchParams({ search, source_id: source, isotope, system, run_number: run, operator, date_from: from, date_to: to }); api(`/calibrations?${query}`).then(setItems).catch(e => onError(e.message)) }
  useEffect(() => { load() }, [])
  return <><div className="filter-grid"><input placeholder="搜索备注或标签" value={search} onChange={e => setSearch(e.target.value)} /><input placeholder="Source ID" value={source} onChange={e => setSource(e.target.value)} /><input placeholder="核素" value={isotope} onChange={e => setIsotope(e.target.value)} /><input placeholder="刻度系统" value={system} onChange={e => setSystem(e.target.value)} /><input placeholder="Run Number" value={run} onChange={e => setRun(e.target.value)} /><input placeholder="操作人" value={operator} onChange={e => setOperator(e.target.value)} /><label>起始日期<input type="date" value={from} onChange={e => setFrom(e.target.value)} /></label><label>结束日期<input type="date" value={to} onChange={e => setTo(e.target.value)} /></label><button className="primary compact" onClick={load}>筛选</button><button className="secondary compact" onClick={() => download(`/calibrations/export.csv?${new URLSearchParams({ search, source_id: source, isotope, system, run_number: run, operator, date_from: from, date_to: to })}`)}>导出 CSV</button></div><Panel title={`${items.length} 条刻度记录`}><div className="table-wrap"><table><thead><tr><th>日期</th><th>Source</th><th>核素</th><th>系统</th><th>Run</th><th>位置</th><th>操作人</th><th>刻度时活度</th></tr></thead><tbody>{items.map(item => <tr key={item.id} onClick={() => navigate(`/calibrations/${item.id}`)}><td>{item.calibration_date || '—'}</td><td className="mono">{item.source_id || item.source_label_raw || '未关联'}</td><td>{item.isotope || '—'}</td><td>{item.calibration_system || '—'}</td><td className="mono">{item.run_number || '—'}</td><td>{item.position_label || '—'}</td><td>{item.operator || '—'}</td><td>{item.activity_at_calibration_bq ? formatBq(item.activity_at_calibration_bq) : '—'}</td></tr>)}</tbody></table>{!items.length && <Empty text="暂无刻度记录" />}</div></Panel></>
}
function AuditPage({ onError }) {
  const [items, setItems] = useState([])
  useEffect(() => { api('/audit').then(setItems).catch(e => onError(e.message)) }, [onError])
  return <Panel title={`${items.length} 条审计记录`}><div className="table-wrap"><table><thead><tr><th>时间</th><th>用户</th><th>动作</th><th>实体</th><th>实体 ID</th><th>来源 IP</th></tr></thead><tbody>{items.map(item => <tr key={item.id}><td>{formatDate(item.created_at)}</td><td>{item.username || '系统'}</td><td className="mono">{item.action}</td><td>{item.entity_type}</td><td className="mono">{item.entity_id}</td><td>{item.ip_address || '—'}</td></tr>)}</tbody></table>{!items.length && <Empty text="暂无审计记录" />}</div></Panel>
}

function AdminPage({ onError }) {
  const [users, setUsers] = useState([]); const [form, setForm] = useState({ username: '', password: '', role: 'viewer' })
  const load = () => api('/admin/users').then(setUsers).catch(e => onError(e.message))
  useEffect(() => { load() }, [])
  const create = async event => { event.preventDefault(); try { await api('/admin/users', { method: 'POST', body: JSON.stringify(form) }); setForm({ username: '', password: '', role: 'viewer' }); load() } catch (e) { onError(e.message) } }
  return <><Panel title="创建本地用户"><form className="inline-form" onSubmit={create}><input required placeholder="用户名" value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} /><input required minLength="8" type="password" placeholder="密码（至少 8 位）" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} /><select value={form.role} onChange={e => setForm({ ...form, role: e.target.value })}><option value="viewer">viewer</option><option value="operator">operator</option><option value="admin">admin</option></select><button className="primary">创建</button></form></Panel><Panel title="用户"><div className="table-wrap"><table><thead><tr><th>用户名</th><th>角色</th><th>状态</th><th>创建时间</th></tr></thead><tbody>{users.map(item => <tr key={item.id}><td>{item.username}</td><td>{item.role}</td><td>{item.is_active ? '启用' : '停用'}</td><td>{formatDate(item.created_at)}</td></tr>)}</tbody></table></div></Panel></>
}

function Panel({ title, children }) { return <section className="panel"><div className="panel-title"><h3>{title}</h3></div>{children}</section> }
function Info({ label, value, mono }) { return <div className="info"><span>{label}</span><b className={mono ? 'mono' : ''}>{value}</b></div> }
function Status({ value }) { return <span className={`status status-${value}`}><i />{statusText[value] || value}</span> }
function SourceMiniList({ items, empty, navigate }) { return items.length ? <div className="mini-list">{items.map(item => <button key={item.source_id} onClick={() => navigate(`/sources/${encodeURIComponent(item.source_id)}`)}><span><b>{item.display_name}</b><small>{item.source_id}</small></span><Status value={item.status} /></button>)}</div> : <Empty text={empty} /> }
function CalibrationRows({ items, navigate }) { return items.length ? <div className="mini-list">{items.slice(0, 8).map(item => <button key={item.id} onClick={() => navigate(`/calibrations/${item.id}`)}><span><b>{item.calibration_date || '—'} · {item.calibration_system || '未命名系统'}</b><small>Run {item.run_number || '—'} · {item.operator || '—'}</small></span><span className="mono">#{item.id}</span></button>)}</div> : <Empty text="暂无刻度记录" /> }
function Empty({ text }) { return <div className="empty">{text}</div> }
function NotFound({ navigate }) { return <Panel title="页面不存在"><p className="muted">当前地址没有对应页面。</p><button className="primary" onClick={() => navigate('/')}>返回总览</button></Panel> }
function formatDate(value) { if (!value) return '—'; try { return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Shanghai' }).format(new Date(value)) } catch { return value } }
function formatBq(value) { if (Math.abs(value) >= 1e6) return `${(value / 1e6).toFixed(2)} MBq`; if (Math.abs(value) >= 1e3) return `${(value / 1e3).toFixed(2)} kBq`; return `${Number(value).toFixed(2)} Bq` }
function formatActivity(activity) { return activity ? `${Number(activity.value).toFixed(2)} ${activity.unit}` : '—' }
function locationText(location) { return location ? [location.building, location.room, location.cabinet, location.position].filter(Boolean).join(' / ') : '' }
function download(path) { window.open(`/api/v1${path}`, '_blank') }

createRoot(document.getElementById('root')).render(<App />)
