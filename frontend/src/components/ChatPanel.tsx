import {useEffect,useState} from 'react'
import {sendChat} from '../api/client'
import type {ChatScope} from '../types'

const suggestions=[
  'How many proposal or RFP emails came in?',
  'How many were marketing versus actual spam we correctly ignored?',
  'Show me everything sitting in triage and why.',
  'Which tasks are high priority but low confidence?',
  'What is the total deal value of all open RFPs?',
  'Did any thread get updated more than once?',
]

type HistoryItem={q:string;a:string;data:Record<string,unknown>;scope:string}

export function ChatPanel({candidate,batch}:{candidate:string;batch:string|null}){
  const[q,setQ]=useState('')
  const[history,setHistory]=useState<HistoryItem[]>([])
  const[busy,setBusy]=useState(false)
  const[error,setError]=useState('')
  const[scopeType,setScopeType]=useState<'batch'|'all'>(batch?'batch':'all')

  useEffect(()=>{
    setScopeType(batch?'batch':'all')
    setHistory([])
    setError('')
  },[batch])

  async function ask(){
    const query=q.trim()
    if(!query||busy)return
    const scope:ChatScope=scopeType==='batch'&&batch?{type:'batch',id:batch}:{type:'all'}
    const scopeLabel=scope.type==='batch'?'current batch':'all history'
    setBusy(true)
    setError('')
    try{
      const r=await sendChat(candidate,query,scope)
      setHistory(h=>[...h,{q:query,a:r.answer,data:r.supporting_data,scope:scopeLabel}])
      setQ('')
    }catch(e){
      setError(e instanceof Error?e.message:String(e))
    }finally{
      setBusy(false)
    }
  }

  return <section className="card chat">
    <div className="section-head">
      <div><span className="step">05</span><h2>Ask grounded questions</h2></div>
      <label className="scope-control">Scope
        <select aria-label="Chat scope" value={scopeType} onChange={e=>setScopeType(e.target.value as 'batch'|'all')}>
          <option value="batch" disabled={!batch}>Current batch</option>
          <option value="all">All history</option>
        </select>
      </label>
    </div>
    {!batch&&<p className="chat-hint">Route the preview to ask about that batch. Until then, questions use all stored history.</p>}
    <div className="suggestions" aria-label="Suggested questions">
      {suggestions.map(s=><button className="question-chip" key={s} onClick={()=>setQ(s)}>{s}</button>)}
    </div>
    {history.map((h,i)=><article key={i}>
      <p className="question">{h.q}</p><span className="answer-scope">{h.scope}</span><p>{h.a}</p>
      <details><summary>Supporting data</summary><pre>{JSON.stringify(h.data,null,2)}</pre></details>
    </article>)}
    {error&&<p className="chat-error" role="alert">Could not answer: {error}</p>}
    <div className="chatbox">
      <input aria-label="Chat question" value={q} onChange={e=>setQ(e.target.value)} onKeyDown={e=>e.key==='Enter'&&ask()} placeholder="How many RFPs were routed?"/>
      <button disabled={busy||!q.trim()} onClick={ask}>{busy?'Checking…':'Ask'}</button>
    </div>
  </section>
}
