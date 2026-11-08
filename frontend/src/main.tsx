import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './ReaderApp'
import './reader.css'

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>)
