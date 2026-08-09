import {useEffect,useRef,useState} from 'react'
import {sendChat} from '../api/client'

const suggestions=[
  'How many proposal or RFP emails came in?',
  'How many were marketing versus actual spam we correctly ignored?',
  'Show me everything sitting in triage and why.',
  'Which tasks are high priority but low confidence?',
  'What is the total deal value of all open RFPs?',
  'Did any thread get updated more than once?',
]

type HistoryItem={q:string;a:string;data:Record<string,unknown>}

export function ChatPanel({candidate,batch}:{candidate:string;batch:string|null}){
  const[q,setQ]=useState('')
  const[history,setHistory]=useState<HistoryItem[]>([])
  const[busy,setBusy]=useState(false)
  const[error,setError]=useState('')
  const historyBox=useRef<HTMLDivElement>(null)

  useEffect(()=>{setHistory([]);setError('');setQ('')},[batch])
  useEffect(()=>{if(historyBox.current)historyBox.current.scrollTop=historyBox.current.scrollHeight},[history,error])

  async function ask(){
    const query=q.trim()
    if(!query||busy||!batch)return
    setBusy(true);setError('')
    try{const response=await sendChat(candidate,query,{type:'batch',id:batch});setHistory(items=>[...items,{q:query,a:response.answer,data:response.supporting_data}]);setQ('')}
    catch(reason){setError(reason instanceof Error?reason.message:String(reason))}
    finally{setBusy(false)}
  }

  return <section className="card chat">
    <div className="section-head"><div><span className="step">05</span><div><h2>Ask grounded questions</h2><p>Answers use only the completed batch and always include supporting data.</p></div></div><span className={`pill chat-state ${batch?'ready':'locked'}`}>{batch?'Current batch ready':'Unlocks after routing'}</span></div>
    {!batch&&<div className="chat-lock" role="status"><span aria-hidden="true">↳</span><div><strong>Your analytics assistant is waiting for routed data.</strong><p>Preview and route the inbox first. Chat unlocks only when every email in this batch has a confirmed outcome.</p></div></div>}
    {batch&&<>
      <div className="suggestions" aria-label="Suggested questions">{suggestions.map(suggestion=><button className="question-chip" key={suggestion} onClick={()=>setQ(suggestion)}>{suggestion}</button>)}</div>
      <div className="chat-history" ref={historyBox} aria-live="polite">
        {!history.length&&!error&&<div className="chat-empty"><strong>Ask about this batch</strong><p>Try a suggested question or type your own. Counts, filters, and totals come from persisted routing data.</p></div>}
        {history.map((item,index)=><article key={index}><p className="question">{item.q}</p><span className="answer-scope">Current routed batch</span><p>{item.a}</p><details><summary>Supporting data</summary><pre>{JSON.stringify(item.data,null,2)}</pre></details></article>)}
        {error&&<p className="chat-error" role="alert">Could not answer: {error}</p>}
      </div>
      <div className="chatbox"><input aria-label="Chat question" value={q} onChange={event=>setQ(event.target.value)} onKeyDown={event=>event.key==='Enter'&&ask()} placeholder="How many RFPs were routed?"/><button disabled={busy||!q.trim()} onClick={ask}>{busy?'Checking…':'Ask'}</button></div>
    </>}
  </section>
}
