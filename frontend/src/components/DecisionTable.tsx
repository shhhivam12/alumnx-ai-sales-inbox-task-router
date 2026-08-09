import type {Decision} from '../types'
import {sendFeedback} from '../api/client'

type DeliveredDecision = Decision & {original_operation?: string;delivery_outcome?: string}

export function DecisionTable({items}:{items:Decision[]}) {
  if (!items.length) return null
  return <section className="card">
    <div className="section-head">
      <div><span className="step">04</span><h2>Decisions</h2></div>
      <span className="pill">Grounded audit trail</span>
    </div>
    <div className="table-wrap"><table>
      <thead><tr><th>Operation</th><th>Email / thread</th><th>Route</th><th>Priority</th><th>Confidence</th><th>Business fields</th><th>Why</th><th>Review</th></tr></thead>
      <tbody>{items.map(item => {
        const decision = item as DeliveredDecision
        const displayedOperation = decision.delivery_outcome || decision.operation
        return <tr key={decision.email_id}>
          <td><span className={`tag ${displayedOperation}`}>{displayedOperation}</span>{displayedOperation === 'unchanged' && <small>Original: {decision.original_operation || decision.operation}</small>}</td>
          <td><code>{decision.email_id}</code><small>{decision.thread_id}</small></td>
          <td>{decision.task ? <><strong>{decision.task.category}</strong><small>{decision.task.assignee_id}</small></> : decision.skip_reason}</td>
          <td>{decision.task?.priority || '—'}</td>
          <td>{Math.round(decision.confidence * 100)}%</td>
          <td><small>{decision.task?.company_name || 'Company unavailable'}</small><small>{decision.task?.due_date || 'No due date'} · {decision.task?.deal_value_inr != null ? `₹${decision.task.deal_value_inr.toLocaleString('en-IN')}` : 'No value'}</small></td>
          <td><details><summary>{decision.reasoning.slice(0, 80)}</summary><p>{decision.reasoning}</p><ul>{decision.evidence.map((e, i) => <li key={i}>{e}</li>)}</ul></details></td>
          <td><select aria-label={`Feedback ${decision.email_id}`} defaultValue="" onChange={event => event.target.value && sendFeedback(decision.email_id, event.target.value)}><option value="" disabled>Label…</option><option value="correct">Correct</option><option value="misrouted">Misrouted</option><option value="missed">Missed</option><option value="spurious">Spurious</option></select></td>
        </tr>
      })}</tbody>
    </table></div>
  </section>
}
