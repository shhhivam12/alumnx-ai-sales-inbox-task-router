import type {Config} from '../types'

const clock=(seconds:number)=>`${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`

export function AppHeader({config,status,wakeSeconds}:{config:Config|null;status:string;wakeSeconds:number}){
  return <header>
    <div><p className="eyebrow">ALUMNX AI LABS · HACKATHON</p><h1>{config?.app_name??'Alumnx AI Sales inbox task router'}</h1><p className="lede">Turn a noisy sales inbox into accountable work—with every routing decision inspectable.</p></div>
    <div className="identity">
      <span className={`status ${status}`}>{status==='waking'?'Waking backend':status}</span>
      {status==='waking'?<div className="cold-start"><i/><div><strong>Please wait — Render is starting the backend.</strong><small>Cold starts can take about a minute. Routing unlocks automatically.</small><time aria-label={`${wakeSeconds} seconds waiting`}>Waiting {clock(wakeSeconds)}</time></div></div>:<><small>Submission identity</small><strong>{config?.candidate_id??'Loading…'}</strong></>}
    </div>
  </header>
}
