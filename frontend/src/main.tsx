import { StrictMode, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import App from './ReaderApp'
import SignIn from './SignIn'
import { auth, onSignedOut, type Session } from './auth'
import './tokens.css'
import './reader.css'

/** Shows the reader to a signed-in account, and the sign-in page otherwise. */
function Gate() {
  const [session, setSession] = useState<Session | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    const check = () =>
      auth<Session>('/session')
        .then((value) => {
          setSession(value)
          setFailed(false)
        })
        .catch(() => setFailed(true))
    void check()
    return onSignedOut(() => void check())
  }, [])
  if (failed)
    return <main className="r-signin"><p className="r-signin-lead">暂时无法连接服务，请稍后刷新。</p></main>
  if (!session) return null
  if (!session.user)
    return <SignIn signup={session.signup} enter={(user) => setSession({ ...session, user })} />
  return <App key={session.user.id} />
}

createRoot(document.getElementById('root')!).render(<StrictMode><Gate /></StrictMode>)
