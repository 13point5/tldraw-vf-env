import React from 'react'
import ReactDOM from 'react-dom/client'
import { ValidatorApp } from './ValidatorApp'
import '../index.css'

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
	<React.StrictMode>
		<ValidatorApp />
	</React.StrictMode>
)
