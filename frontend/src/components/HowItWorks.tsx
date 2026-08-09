const steps=[
  ['1','Load an inbox','Paste JSON, upload a file, or use the sample emails. Nothing is routed yet.'],
  ['2','Check the raw preview','You see the original sender, subject, thread, time, and message before AI touches it.'],
  ['3','Route the batch','The backend cleans each email, ignores quoted history, and identifies the latest request.'],
  ['4','Assign with rules','Gemini extracts meaning; fixed business rules choose the owner, category, priority, and business fields.'],
  ['5','Save every outcome','Created, updated, skipped, and unchanged results are persisted so refreshes and replays stay consistent.'],
  ['6','Audit and ask','The dashboard explains every route. Chat calculates answers from stored batch data instead of guessing.'],
]

export function HowItWorks(){return <section className="how-page">
  <div className="page-intro"><span className="eyebrow">SIMPLE BY DESIGN</span><h2>How Alumnx AI routes a sales inbox</h2><p>A plain-language walkthrough of what happens from upload to grounded answers.</p></div>
  <div className="how-flow">{steps.map(([number,title,body])=><article key={number}><span>{number}</span><div><h3>{title}</h3><p>{body}</p></div></article>)}</div>
  <div className="how-details">
    <section><span className="eyebrow">WHAT AI DOES</span><h3>Understands messy language</h3><p>Gemini identifies intent, organizations, money, deadlines, and whether the sender is buying, selling, collaborating, or sending an automated message.</p></section>
    <section><span className="eyebrow">WHAT RULES DO</span><h3>Keep routing predictable</h3><p>Code—not the model—applies the exact owner precedence, ₹10 lakh threshold, priority boundaries, skip policy, and create-versus-update behavior.</p></section>
    <section><span className="eyebrow">WHAT CHAT DOES</span><h3>Answers from stored facts</h3><p>Your question becomes an allowed analytics query. Postgres supplies the numbers, and the answer is rejected if it changes those supporting facts.</p></section>
  </div>
  <div className="trust-strip"><strong>Safe boundaries</strong><span>The browser never calls Gemini or Supabase directly.</span><span>Email instructions cannot trigger tools or actions.</span><span>Missing values stay empty instead of being invented.</span></div>
</section>}
