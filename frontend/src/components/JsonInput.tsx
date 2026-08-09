import {useRef} from 'react'

export function JsonInput({value,onChange,onParse,onSample,error,disabled=false}:{value:string;onChange:(v:string)=>void;onParse:()=>void;onSample:()=>void;error:string;disabled?:boolean}){
  const input=useRef<HTMLInputElement>(null)
  return <section className="card">
    <div className="section-head"><div><span className="step">01</span><div><h2>Load the inbox</h2><p>Paste JSON, upload a file, or start with the built-in sample batch.</p></div></div><button className="ghost" disabled={disabled} onClick={onSample}>Load 250 samples</button></div>
    <textarea aria-label="Email JSON" disabled={disabled} value={value} onChange={e=>onChange(e.target.value)} placeholder='Paste an email array or {"candidate_id":"…","emails":[]}'/>
    <div className="actions"><button disabled={disabled} onClick={onParse}>Preview JSON</button><button className="secondary" disabled={disabled} onClick={()=>input.current?.click()}>Upload .json</button><input ref={input} hidden disabled={disabled} type="file" accept="application/json,.json" onChange={async e=>{const file=e.target.files?.[0];if(file)onChange(await file.text())}}/></div>
    {disabled&&<p className="input-lock">Input is locked while this batch is routing.</p>}{error&&<p className="error">{error}</p>}
  </section>
}
