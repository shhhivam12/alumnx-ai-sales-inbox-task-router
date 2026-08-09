export type AppView='inbox'|'team'|'how'

const items:[AppView,string,string][]=[
  ['inbox','Inbox router','Route and audit a batch'],
  ['team','Team analytics','Workload and attention'],
  ['how','How it works','A simple walkthrough'],
]

export function AppNav({view,onChange}:{view:AppView;onChange:(view:AppView)=>void}){
  return <nav className="app-nav" aria-label="Application sections">
    {items.map(([id,label,description])=><button key={id} className={view===id?'active':''} aria-current={view===id?'page':undefined} onClick={()=>onChange(id)}><strong>{label}</strong><small>{description}</small></button>)}
  </nav>
}
