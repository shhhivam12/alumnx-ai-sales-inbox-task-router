import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {expect,test,vi} from 'vitest'

import App from '../src/App'


const config={app_name:'Alumnx AI Sales inbox task router',candidate_id:'mahendrushivam123@gmail.com',max_ingest_emails:100}
const email={email_id:'e1',thread_id:'t1',message_index:0,from_name:'Buyer',from_email:'buyer@example.com',to:'sales@example.com',cc:[],subject:'Demo',body:'Please arrange a demo.',received_at:'2026-08-09T10:00:00+05:30',attachments:[],is_reply:false}

test('invalid JSON never invokes ingest and preview precedes routing',async()=>{
  const fetchMock=vi.fn(async(input:RequestInfo|URL)=>{
    const url=String(input)
    if(url.endsWith('/api/config'))return new Response(JSON.stringify(config),{status:200})
    if(url.endsWith('/ready'))return new Response(JSON.stringify({status:'ready'}),{status:200})
    return new Response('{}',{status:500})
  })
  vi.stubGlobal('fetch',fetchMock)
  render(<App/>)
  const editor=screen.getByLabelText('Email JSON')
  fireEvent.change(editor,{target:{value:'{'}})
  fireEvent.click(screen.getByText('Preview JSON'))
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not complete')
  expect(fetchMock.mock.calls.some(c=>String(c[0]).endsWith('/ingest'))).toBe(false)
})

test('editing a routed preview clears the stale current-batch chat scope',async()=>{
  const fetchMock=vi.fn(async(input:RequestInfo|URL)=>{
    const url=String(input)
    if(url.endsWith('/api/config'))return new Response(JSON.stringify(config),{status:200})
    if(url.endsWith('/ready'))return new Response(JSON.stringify({status:'ready'}),{status:200})
    if(url.endsWith('/ingest'))return new Response(JSON.stringify({run_id:'run-1',processed:1,tasks_created:1,tasks_updated:0,skipped:0,unchanged:0,errors:[]}),{status:200})
    if(url.includes('/api/batches/'))return new Response(JSON.stringify({items:[]}),{status:200})
    return new Response('{}',{status:500})
  })
  vi.stubGlobal('fetch',fetchMock)
  render(<App/>)
  await screen.findByText('ready')
  const editor=screen.getByLabelText('Email JSON')
  fireEvent.change(editor,{target:{value:JSON.stringify([email])}})
  fireEvent.click(screen.getByText('Preview JSON'))
  fireEvent.click(screen.getByRole('button',{name:'Route emails'}))
  await waitFor(()=>expect(screen.getByLabelText('Chat scope')).toHaveValue('batch'))

  fireEvent.change(editor,{target:{value:JSON.stringify([{...email,email_id:'e2'}])}})
  await waitFor(()=>expect(screen.getByLabelText('Chat scope')).toHaveValue('all'))
  expect(screen.getByRole('option',{name:'Current batch'})).toBeDisabled()
})
