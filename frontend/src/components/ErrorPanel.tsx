export function ErrorPanel({message}:{message:string}){return message?<div role="alert" className="error-panel"><strong>Could not complete the request</strong><span>{message}</span></div>:null}
