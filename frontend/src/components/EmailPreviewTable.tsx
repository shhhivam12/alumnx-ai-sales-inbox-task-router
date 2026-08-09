import {useEffect,useState} from 'react'
import type {Email} from '../types'
import {Pagination} from './Pagination'

export function EmailPreviewTable({emails}:{emails:Email[]}){
  const[page,setPage]=useState(1)
  const[pageSize,setPageSize]=useState(20)
  const pages=Math.max(1,Math.ceil(emails.length/pageSize))
  useEffect(()=>setPage(1),[emails])
  useEffect(()=>{if(page>pages)setPage(pages)},[page,pages])
  if(!emails.length)return null
  const visible=emails.slice((page-1)*pageSize,page*pageSize)
  return <section className="card">
    <div className="section-head"><div><span className="step">02</span><h2>Raw preview</h2></div><span className="pill">{emails.length} emails · nothing routed yet</span></div>
    <div className="table-wrap"><table><thead><tr><th>Sender</th><th>Subject</th><th>Received</th><th>Thread</th><th>Body preview</th></tr></thead><tbody>{visible.map(email=><tr key={email.email_id}><td><strong>{email.from_name}</strong><small>{email.from_email}</small></td><td>{email.subject||<em>Empty subject</em>}</td><td>{new Date(email.received_at).toLocaleString()}</td><td><code>{email.thread_id}</code></td><td><details><summary>{email.body.slice(0,100)}{email.body.length>100?'…':''}</summary><pre>{email.body}</pre></details></td></tr>)}</tbody></table></div>
    <Pagination page={page} pageSize={pageSize} total={emails.length} onPage={setPage} onPageSize={size=>{setPageSize(size);setPage(1)}} label="Raw emails"/>
  </section>
}
