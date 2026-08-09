import {useEffect,useState} from 'react'
import type {Decision,Email} from '../types'
import {sendFeedback} from '../api/client'
import {Pagination} from './Pagination'

type DeliveredDecision=Decision&{original_operation?:string;delivery_outcome?:string}

export function DecisionTable({items,emails=[],live=false}:{items:Decision[];emails?:Email[];live?:boolean}){
  const[page,setPage]=useState(1)
  const[pageSize,setPageSize]=useState(20)
  const pages=Math.max(1,Math.ceil(items.length/pageSize))
  useEffect(()=>{if(page>pages)setPage(pages)},[page,pages])
  const emailById=new Map(emails.map(email=>[email.email_id,email]))
  const visible=items.slice((page-1)*pageSize,page*pageSize)
  return <section className="card decision-feed">
    <div className="section-head audit-heading"><div><span className="step">06</span><div><span className="eyebrow">AUDIT STREAM</span><h2>Every routing decision</h2></div></div><span className="pill">{live?'Updating live':`${items.length} persisted`}</span></div>
    {!items.length&&<div className="decision-wait"><i/><div><strong>Waiting for the first confirmed decision…</strong><small>Rows appear here only after they are persisted by the backend.</small></div></div>}
    {!!items.length&&<><div className="table-wrap"><table>
      <thead><tr><th>Outcome</th><th>Email</th><th>Assigned to</th><th>Priority</th><th>Confidence</th><th>Business fields</th><th>Why</th><th>Review</th></tr></thead>
      <tbody>{visible.map(item=>{
        const decision=item as DeliveredDecision
        const displayedOperation=decision.delivery_outcome||decision.operation
        const email=emailById.get(decision.email_id)
        return <tr key={decision.email_id}>
          <td><span className={`tag ${displayedOperation}`}>{displayedOperation}</span>{displayedOperation==='unchanged'&&<small>Original: {decision.original_operation||decision.operation}</small>}</td>
          <td><strong>{email?.subject||decision.email_id}</strong><small>{email?.from_name||decision.email_id} · {decision.thread_id}</small></td>
          <td>{decision.task?<><strong>{decision.task.assignee_id}</strong><small>{decision.task.category}</small></>:<><strong>Not assigned</strong><small>{decision.skip_reason}</small></>}</td>
          <td>{decision.task?.priority||'—'}</td>
          <td><div className="confidence-cell"><strong>{Math.round(decision.confidence*100)}%</strong><span><i style={{width:`${Math.round(decision.confidence*100)}%`}}/></span></div></td>
          <td><small>{decision.task?.company_name||'Company unavailable'}</small><small>{decision.task?.due_date||'No due date'} · {decision.task?.deal_value_inr!=null?`₹${decision.task.deal_value_inr.toLocaleString('en-IN')}`:'No value'}</small></td>
          <td><details><summary>{decision.reasoning.slice(0,80)}</summary><p>{decision.reasoning}</p><ul>{(decision.evidence||[]).map((e,index)=><li key={index}>{e}</li>)}</ul></details></td>
          <td><select aria-label={`Feedback ${decision.email_id}`} defaultValue="" onChange={event=>event.target.value&&sendFeedback(decision.email_id,event.target.value)}><option value="" disabled>Label…</option><option value="correct">Correct</option><option value="misrouted">Misrouted</option><option value="missed">Missed</option><option value="spurious">Spurious</option></select></td>
        </tr>
      })}</tbody>
    </table></div><Pagination page={page} pageSize={pageSize} total={items.length} onPage={setPage} onPageSize={size=>{setPageSize(size);setPage(1)}} label="Routing decisions"/></>}
  </section>
}
