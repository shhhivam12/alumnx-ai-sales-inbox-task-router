export function Pagination({page,pageSize,total,onPage,onPageSize,label}:{page:number;pageSize:number;total:number;onPage:(page:number)=>void;onPageSize:(size:number)=>void;label:string}){
  const pages=Math.max(1,Math.ceil(total/pageSize))
  const start=total?((page-1)*pageSize)+1:0
  const end=Math.min(total,page*pageSize)
  return <div className="pagination" aria-label={`${label} pagination`}>
    <div><strong>{start}–{end}</strong><span>of {total}</span></div>
    <nav aria-label={`${label} pages`}>
      <button className="page-arrow" disabled={page===1} onClick={()=>onPage(page-1)} aria-label={`Previous ${label} page`}>←</button>
      {Array.from({length:pages},(_,index)=>index+1).map(number=><button className={number===page?'active':''} aria-current={number===page?'page':undefined} key={number} onClick={()=>onPage(number)}>{number}</button>)}
      <button className="page-arrow" disabled={page===pages} onClick={()=>onPage(page+1)} aria-label={`Next ${label} page`}>→</button>
    </nav>
    <label>Rows
      <select aria-label={`${label} rows per page`} value={pageSize} onChange={event=>onPageSize(Number(event.target.value))}>
        {[10,20,50,100].map(size=><option key={size} value={size}>{size}</option>)}
      </select>
    </label>
  </div>
}
