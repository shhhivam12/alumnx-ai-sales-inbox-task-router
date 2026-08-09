import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {expect,test,vi} from 'vitest'

import {ChatPanel} from '../src/components/ChatPanel'


test('uses explicit batch/all scopes and renders supporting data',async()=>{
  const fetchMock=vi.fn(async(_input:RequestInfo|URL,init?:RequestInit)=>{
    const request=JSON.parse(String(init?.body))
    return new Response(JSON.stringify({answer:'There are 0 GST refund decisions.',supporting_data:{gst_refund_count:0},scope:request.scope}),{status:200})
  })
  vi.stubGlobal('fetch',fetchMock)
  render(<ChatPanel candidate="mahendrushivam123@gmail.com" batch="11111111-1111-4111-8111-111111111111"/>)
  expect(screen.getByLabelText('Chat scope')).toHaveValue('batch')

  fireEvent.click(screen.getByRole('button',{name:'How many proposal or RFP emails came in?'}))
  fireEvent.click(screen.getByRole('button',{name:'Ask'}))
  expect(await screen.findByText('There are 0 GST refund decisions.')).toBeVisible()
  fireEvent.click(screen.getByText('Supporting data'))
  expect(screen.getByText(/"gst_refund_count": 0/)).toBeVisible()
  expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body)).scope).toEqual({type:'batch',id:'11111111-1111-4111-8111-111111111111'})

  fireEvent.change(screen.getByLabelText('Chat scope'),{target:{value:'all'}})
  fireEvent.change(screen.getByLabelText('Chat question'),{target:{value:'Were there any GST refunds?'}})
  fireEvent.click(screen.getByRole('button',{name:'Ask'}))
  await waitFor(()=>expect(fetchMock).toHaveBeenCalledTimes(2))
  expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body)).scope).toEqual({type:'all'})
})

test('shows a useful error and resets old answers when the batch changes',async()=>{
  const fetchMock=vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({answer:'Grounded answer',supporting_data:{count:1},scope:{type:'batch',id:'batch-one'}}),{status:200}))
    .mockResolvedValueOnce(new Response(JSON.stringify({error:{message:'Backend unavailable'}}),{status:503}))
  vi.stubGlobal('fetch',fetchMock)
  const view=render(<ChatPanel candidate="mahendrushivam123@gmail.com" batch="batch-one"/>)
  fireEvent.change(screen.getByLabelText('Chat question'),{target:{value:'How many RFPs?'}})
  fireEvent.click(screen.getByRole('button',{name:'Ask'}))
  expect(await screen.findByText('Grounded answer')).toBeVisible()

  view.rerender(<ChatPanel candidate="mahendrushivam123@gmail.com" batch="batch-two"/>)
  await waitFor(()=>expect(screen.queryByText('Grounded answer')).not.toBeInTheDocument())
  fireEvent.change(screen.getByLabelText('Chat question'),{target:{value:'How many RFPs?'}})
  fireEvent.click(screen.getByRole('button',{name:'Ask'}))
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not answer: Backend unavailable')
})
