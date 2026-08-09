import type {Decision,TeamMember} from '../types'

const categoryOrder=['enterprise_rfp','smb_enquiry','marketing','alliances','finance','triage']

function currentTasks(decisions:Decision[]){
  const current=new Map<string,Decision>()
  for(const decision of decisions)if(decision.task)current.set(decision.thread_id,decision)
  return [...current.values()]
}

export function TeamAnalytics({team,decisions,routing,complete}:{team:TeamMember[];decisions:Decision[];routing:boolean;complete:boolean}){
  const tasks=currentTasks(decisions)
  const rows=team.map(person=>{
    const owned=tasks.filter(decision=>decision.task?.assignee_id===person.user_id)
    return {...person,tasks:owned.length,high:owned.filter(d=>d.task?.priority==='high').length,medium:owned.filter(d=>d.task?.priority==='medium').length,low:owned.filter(d=>d.task?.priority==='low').length,deadlines:owned.filter(d=>d.task?.due_date).length,lowConfidence:owned.filter(d=>d.confidence<=.54).length}
  })
  const maxLoad=Math.max(1,...rows.map(row=>row.tasks))
  const totalHigh=rows.reduce((sum,row)=>sum+row.high,0)
  const totalDeadlines=rows.reduce((sum,row)=>sum+row.deadlines,0)
  const totalLowConfidence=rows.reduce((sum,row)=>sum+row.lowConfidence,0)
  const heaviest=rows.reduce((best,row)=>row.tasks>best.tasks?row:best,rows[0]||{name:'No one',tasks:0})
  const categoryCounts=Object.fromEntries(categoryOrder.map(category=>[category,tasks.filter(d=>d.task?.category===category).length])) as Record<string,number>
  const maxCategory=Math.max(1,...Object.values(categoryCounts))

  return <section className="team-page" aria-live="polite">
    <div className="page-intro team-intro"><div><span className="eyebrow">OPS MANAGER VIEW</span><h2>Team analytics</h2><p>See how this batch distributes work, urgency, deadlines, and review risk across the routing personas.</p></div><span className={`pill ${routing?'team-live':''}`}>{routing?'Updating as routes persist':complete?'Current batch complete':'Waiting for a routed batch'}</span></div>
    <div className="team-summary">
      <article><span>Current tasks</span><strong>{tasks.length}</strong><small>One current task per routed thread</small></article>
      <article><span>High priority</span><strong>{totalHigh}</strong><small>Needs prompt attention</small></article>
      <article><span>Dated deadlines</span><strong>{totalDeadlines}</strong><small>Explicit actionable dates only</small></article>
      <article><span>Low confidence</span><strong>{totalLowConfidence}</strong><small>Best candidates for review</small></article>
      <article><span>Highest batch load</span><strong>{heaviest.tasks?heaviest.name.split(' ')[0]:'—'}</strong><small>{heaviest.tasks} current tasks</small></article>
    </div>
    <div className="team-card-grid">{rows.map(person=>{
      const share=tasks.length?Math.round(person.tasks/tasks.length*100):0
      return <article key={person.user_id}>
        <div className="team-card-title"><span>{person.name.split(' ').map(part=>part[0]).join('').slice(0,2)}</span><div><h3>{person.name}</h3><p>{person.department}</p></div><strong>{person.tasks}</strong></div>
        <p>{person.scope}</p><div className="team-load-track"><i style={{width:`${person.tasks/maxLoad*100}%`}}/></div><small>{share}% of current batch tasks</small>
        <dl><div><dt>High</dt><dd>{person.high}</dd></div><div><dt>Medium</dt><dd>{person.medium}</dd></div><div><dt>Low</dt><dd>{person.low}</dd></div><div><dt>Deadlines</dt><dd>{person.deadlines}</dd></div><div><dt>Review</dt><dd>{person.lowConfidence}</dd></div></dl>
      </article>
    })}</div>
    <div className="team-charts">
      <section><div className="insight-heading"><div><span className="eyebrow">WORKLOAD</span><h3>Assignments by owner</h3></div><small>Current thread tasks</small></div><div className="owner-bars">{rows.map(row=><div key={row.user_id}><label><span>{row.name}</span><strong>{row.tasks}</strong></label><div><i style={{width:`${row.tasks/maxLoad*100}%`}}/></div></div>)}</div></section>
      <section><div className="insight-heading"><div><span className="eyebrow">PRIORITY MIX</span><h3>Attention by owner</h3></div><small>High / medium / low</small></div><div className="priority-matrix">{rows.map(row=>{const total=Math.max(1,row.tasks);return <div key={row.user_id}><label>{row.name.split(' ')[0]}</label><div><i className="high" style={{width:`${row.high/total*100}%`}}/><i className="medium" style={{width:`${row.medium/total*100}%`}}/><i className="low" style={{width:`${row.low/total*100}%`}}/></div><strong>{row.high} / {row.medium} / {row.low}</strong></div>})}</div></section>
      <section><div className="insight-heading"><div><span className="eyebrow">WORK MIX</span><h3>Categories in this batch</h3></div><small>Current task category</small></div><div className="owner-bars">{categoryOrder.map(category=><div key={category}><label><span>{category.replace('_',' ')}</span><strong>{categoryCounts[category]}</strong></label><div><i style={{width:`${categoryCounts[category]/maxCategory*100}%`}}/></div></div>)}</div></section>
    </div>
    <p className="status-caveat"><strong>Status note:</strong> the challenge Task API has no open or completed field. These figures describe current routed tasks and priority—not verified pending work.</p>
  </section>
}
