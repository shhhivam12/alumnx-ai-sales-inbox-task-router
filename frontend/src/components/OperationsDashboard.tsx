import type {Decision,Email,IngestResult,TeamMember} from '../types'

const categories=['enterprise_rfp','smb_enquiry','marketing','alliances','finance','triage']
const effectiveOperation=(decision:Decision)=>decision.delivery_outcome||decision.operation

function latestTasks(decisions:Decision[]){
  const tasks=new Map<string,Decision>()
  for(const decision of decisions)if(decision.task)tasks.set(decision.thread_id,decision)
  return [...tasks.values()]
}

export function OperationsDashboard({emails,decisions,results,team,routing,complete}:{emails:Email[];decisions:Decision[];results:IngestResult[];team:TeamMember[];routing:boolean;complete:boolean}){
  if(!routing&&!decisions.length&&!results.length)return null
  const current=latestTasks(decisions)
  const resultTotals=results.reduce((sum,result)=>({processed:sum.processed+result.processed,created:sum.created+result.tasks_created,updated:sum.updated+result.tasks_updated,skipped:sum.skipped+result.skipped,unchanged:sum.unchanged+result.unchanged,errors:sum.errors+result.errors.length}),{processed:0,created:0,updated:0,skipped:0,unchanged:0,errors:0})
  const liveTotals={processed:decisions.length,created:decisions.filter(d=>effectiveOperation(d)==='create').length,updated:decisions.filter(d=>effectiveOperation(d)==='update').length,skipped:decisions.filter(d=>effectiveOperation(d)==='skip').length,unchanged:decisions.filter(d=>effectiveOperation(d)==='unchanged').length,errors:0}
  const totals=complete?resultTotals:liveTotals
  const high=current.filter(d=>d.task?.priority==='high').length
  const lowConfidence=current.filter(d=>d.confidence<=.54).length
  const triage=current.filter(d=>d.task?.category==='triage').length
  const knownValue=current.reduce((sum,d)=>sum+(d.task?.deal_value_inr||0),0)
  const categoryCounts=Object.fromEntries(categories.map(category=>[category,current.filter(d=>d.task?.category===category).length])) as Record<string,number>
  const maxCategory=Math.max(1,...Object.values(categoryCounts))
  const deadlines=current.filter(d=>d.task?.due_date).sort((a,b)=>String(a.task?.due_date).localeCompare(String(b.task?.due_date)))
  const urgentDeadlines=deadlines.filter(d=>d.task?.priority==='high')
  const workload=team.map(person=>{
    const assigned=current.filter(d=>d.task?.assignee_id===person.user_id)
    return {...person,count:assigned.length,high:assigned.filter(d=>d.task?.priority==='high').length,lowConfidence:assigned.filter(d=>d.confidence<=.54).length}
  })
  const maxLoad=Math.max(1,...workload.map(person=>person.count))
  const progress=emails.length?Math.min(100,Math.round(decisions.length/emails.length*100)):0

  return <section className="card operations-dashboard" aria-live="polite">
    <div className="section-head dashboard-head">
      <div><span className="step">04</span><div><h2>Live routing dashboard</h2><p>{routing?'Watching confirmed decisions as they are persisted.':'Every number below belongs to this routed batch.'}</p></div></div>
      <span className={`pill live-pill ${routing?'processing':'complete'}`}><i/>{routing?'Routing in progress':complete?'Batch complete':'Preparing results'}</span>
    </div>
    <div className="routing-meter" aria-label={`${progress}% of email decisions visible`}><div><span>Persisted decisions</span><strong>{decisions.length} / {emails.length}</strong></div><progress value={decisions.length} max={Math.max(1,emails.length)}/><small>{progress}% visible · Chat unlocks at 100%</small></div>
    <div className="dashboard-kpis">
      <div><span>Processed</span><strong>{totals.processed}</strong><small>{totals.created} created · {totals.updated} updated</small></div>
      <div><span>Human review</span><strong>{triage}</strong><small>{lowConfidence} low-confidence tasks</small></div>
      <div><span>Priority pressure</span><strong>{high}</strong><small>{urgentDeadlines.length} with dated deadlines</small></div>
      <div><span>Known deal value</span><strong>₹{knownValue.toLocaleString('en-IN')}</strong><small>Null values are excluded</small></div>
      <div><span>Correctly ignored</span><strong>{totals.skipped}</strong><small>{totals.unchanged} unchanged deliveries</small></div>
      <div><span>Errors</span><strong>{totals.errors}</strong><small>{totals.errors?'Review the error panel':'No processing failures'}</small></div>
    </div>
    <div className="dashboard-grid">
      <section className="insight-panel persona-panel">
        <div className="insight-heading"><div><span className="eyebrow">TEAM LOAD</span><h3>Who owns the work?</h3></div><small>Current tasks, not email volume</small></div>
        <div className="persona-grid">{workload.map(person=>{
          const concentration=current.length?person.count/current.length:0
          const loadWatch=person.count>=5&&concentration>=.4
          return <article className={`persona-card ${loadWatch?'load-watch':''}`} key={person.user_id}>
            <div className="persona-top"><span className="avatar">{person.name.split(' ').map(part=>part[0]).join('').slice(0,2)}</span><div><strong>{person.name}</strong><small>{person.department}</small></div><b>{person.count}</b></div>
            <p>{person.scope}</p><div className="mini-bar"><i style={{width:`${person.count/maxLoad*100}%`}}/></div>
            <footer><span>{person.high} high priority</span><span>{person.lowConfidence} low confidence</span></footer>
            {loadWatch&&<em>Load watch · {Math.round(concentration*100)}% of this batch</em>}
          </article>
        })}</div>
        <p className="analytics-caveat">“Load watch” means this person owns at least 40% of five or more current batch tasks. It indicates concentration, not employee capacity.</p>
      </section>
      <section className="insight-panel category-panel">
        <div className="insight-heading"><div><span className="eyebrow">WORK MIX</span><h3>Task distribution</h3></div><small>{current.length} current tasks</small></div>
        <div className="bar-chart">{categories.map(category=><div key={category}><label><span>{category.replace('_',' ')}</span><strong>{categoryCounts[category]}</strong></label><div><i style={{width:`${categoryCounts[category]/maxCategory*100}%`}}/></div></div>)}</div>
      </section>
      <section className="insight-panel deadline-panel">
        <div className="insight-heading"><div><span className="eyebrow">DEADLINE RADAR</span><h3>What needs attention?</h3></div><small>{deadlines.length} dated tasks</small></div>
        {!deadlines.length?<p className="empty-insight">No explicit actionable deadlines in the persisted results so far.</p>:<ol>{deadlines.slice(0,5).map(decision=><li key={decision.thread_id}><span className={`priority-dot ${decision.task?.priority}`}/><div><strong>{decision.task?.company_name||decision.thread_id}</strong><small>{decision.task?.category?.replace('_',' ')} · {decision.task?.assignee_id}</small></div><time>{decision.task?.due_date}</time></li>)}</ol>}
        {deadlines.length>5&&<p className="more-deadlines">+ {deadlines.length-5} more dated tasks in the decision stream</p>}
      </section>
    </div>
  </section>
}
