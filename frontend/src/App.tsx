import {useEffect,useState} from 'react'
import {getConfig,getDecisions,getReady,getSamples,getUsers,ingest} from './api/client'
import {AppHeader} from './components/AppHeader'
import {AppNav,type AppView} from './components/AppNav'
import {JsonInput} from './components/JsonInput'
import {EmailPreviewTable} from './components/EmailPreviewTable'
import {RoutingProgress} from './components/RoutingProgress'
import {OperationsDashboard} from './components/OperationsDashboard'
import {ChatPanel} from './components/ChatPanel'
import {DecisionTable} from './components/DecisionTable'
import {TeamAnalytics} from './components/TeamAnalytics'
import {HowItWorks} from './components/HowItWorks'
import {ErrorPanel} from './components/ErrorPanel'
import type {Config,Decision,Email,IngestResult,TeamMember} from './types'
import {chunkEmails,validateEmails} from './features/input/validation'
import './styles.css'
import './dashboard.css'
import './workspace.css'
import './mobile.css'

const fallbackTeam:TeamMember[]=[
  {user_id:'u_aarti',name:'Aarti Menon',department:'Sales — Enterprise',scope:'RFPs, RFIs, tenders, and inbound deals above ₹10,00,000'},
  {user_id:'u_rohit',name:'Rohit Sharma',department:'Sales — SMB',scope:'Product enquiries, demos, and deals at or below ₹10,00,000'},
  {user_id:'u_meera',name:'Meera Iyer',department:'Marketing',scope:'Webinars, sponsorships, content collaborations, PR, and media'},
  {user_id:'u_karan',name:'Karan Doshi',department:'Alliances',scope:'Reseller, channel partner, and technology integration proposals'},
  {user_id:'u_divya',name:'Divya Rao',department:'Finance',scope:'Invoices, purchase orders, payments, GST, and vendor billing'},
  {user_id:'u_triage',name:'Triage Queue',department:'Operations',scope:'Ambiguous items requiring human review'},
]

export default function App(){
  const[view,setView]=useState<AppView>('inbox')
  const[config,setConfig]=useState<Config|null>(null)
  const[team,setTeam]=useState<TeamMember[]>(fallbackTeam)
  const[status,setStatus]=useState('waking')
  const[wakeSeconds,setWakeSeconds]=useState(0)
  const[text,setText]=useState('')
  const[emails,setEmails]=useState<Email[]>([])
  const[error,setError]=useState('')
  const[routing,setRouting]=useState(false)
  const[progress,setProgress]=useState([0,0])
  const[results,setResults]=useState<IngestResult[]>([])
  const[decisions,setDecisions]=useState<Decision[]>([])
  const[batch,setBatch]=useState<string|null>(null)

  useEffect(()=>{if(status!=='waking')return;const timer=window.setInterval(()=>setWakeSeconds(seconds=>seconds+1),1000);return()=>window.clearInterval(timer)},[status])
  useEffect(()=>{let stopped=false;(async()=>{
    let lastError:unknown
    for(let attempt=0;attempt<48;attempt++){
      try{
        const loaded=await getConfig();if(stopped)return;setConfig(loaded)
        getUsers().then(response=>!stopped&&setTeam(response.team)).catch(()=>undefined)
        await getReady();if(!stopped){setStatus('ready');setError('')}return
      }catch(reason){lastError=reason;if(!stopped)setStatus('waking');await new Promise(resolve=>setTimeout(resolve,2500))}
    }
    if(!stopped){setStatus('offline');setError(`Backend did not become ready: ${lastError instanceof Error?lastError.message:String(lastError)}`)}
  })();return()=>{stopped=true}},[])

  function clearRoutedState(){setResults([]);setDecisions([]);setBatch(null);setProgress([0,0])}
  function changeText(value:string){if(routing)return;setText(value);setEmails([]);clearRoutedState();setError('')}
  function parse(){try{setEmails(validateEmails(JSON.parse(text)));setError('');clearRoutedState()}catch(reason){setError(reason instanceof Error?reason.message:String(reason));setEmails([]);clearRoutedState()}}
  async function samples(){try{const response=await getSamples();setText(JSON.stringify(response.emails,null,2));setEmails(response.emails);setError('');clearRoutedState()}catch(reason){setError(reason instanceof Error?reason.message:String(reason))}}
  async function route(){
    if(!config||!emails.length||routing)return
    const id=crypto.randomUUID()
    const chunks=chunkEmails(emails,config.max_ingest_emails)
    let timer:number|undefined
    let pollBusy=false
    let polling=true
    const refresh=async()=>{if(pollBusy||!polling)return;pollBusy=true;try{const response=await getDecisions(id);if(polling)setDecisions(response.items)}catch{/* The ingest request remains authoritative. */}finally{pollBusy=false}}
    setRouting(true);setBatch(null);setProgress([0,chunks.length]);setResults([]);setDecisions([]);setError('')
    timer=window.setInterval(refresh,1500)
    try{
      const completed:IngestResult[]=[]
      for(let index=0;index<chunks.length;index++){completed.push(await ingest(config.candidate_id,id,chunks[index]));setResults([...completed]);setProgress([index+1,chunks.length]);await refresh()}
      await refresh();polling=false
      const finalDecisions=await getDecisions(id);setDecisions(finalDecisions.items);setBatch(id)
    }catch(reason){polling=false;setError(reason instanceof Error?reason.message:String(reason))}
    finally{if(timer!==undefined)window.clearInterval(timer);setRouting(false)}
  }

  const complete=Boolean(batch)&&!routing
  return <main>
    <AppHeader config={config} status={status} wakeSeconds={wakeSeconds}/>
    <AppNav view={view} onChange={setView}/>
    <div hidden={view!=='inbox'}>
      <JsonInput value={text} onChange={changeText} onParse={parse} onSample={samples} error="" disabled={routing}/>
      <ErrorPanel message={error}/>
      <EmailPreviewTable emails={emails}/>
      {emails.length>0&&<RoutingProgress done={progress[0]} total={progress[1]} routing={routing} ready={status==='ready'} onRoute={route}/>}
      <OperationsDashboard emails={emails} decisions={decisions} results={results} team={team} routing={routing} complete={complete}/>
      {config&&<ChatPanel candidate={config.candidate_id} batch={batch}/>}
      {(routing||decisions.length>0)&&<DecisionTable items={decisions} emails={emails} live={routing}/>}
    </div>
    {view==='team'&&<TeamAnalytics team={team} decisions={decisions} routing={routing} complete={complete}/>}
    {view==='how'&&<HowItWorks/>}
    <footer className="site-footer"><span>Made with <b>♥</b> by Shivam Mahendru</span><nav aria-label="Shivam Mahendru social links"><a href="https://www.linkedin.com/in/shivam-mahendru-5b212b203/" target="_blank" rel="noreferrer">LinkedIn</a><a href="https://github.com/shhhivam12" target="_blank" rel="noreferrer">GitHub</a></nav></footer>
  </main>
}
