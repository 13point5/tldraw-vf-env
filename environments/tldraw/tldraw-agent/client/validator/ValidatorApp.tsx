import { useEffect } from 'react'
import { DefaultSizeStyle, Tldraw, TldrawUiToastsProvider, useEditor } from 'tldraw'
import { useTldrawAgent } from '../agent/useTldrawAgent'
import { attachValidatorBridge } from './bridge'

const AGENT_ID = 'validator-agent'

DefaultSizeStyle.setDefaultValue('s')

export function ValidatorApp() {
	return (
		<TldrawUiToastsProvider>
			<div className="tldraw-validator-container">
				<Tldraw>
					<ValidatorInner />
				</Tldraw>
			</div>
		</TldrawUiToastsProvider>
	)
}

function ValidatorInner() {
	const editor = useEditor()
	const agent = useTldrawAgent(editor, AGENT_ID)

	useEffect(() => {
		if (!editor || !agent) return
		;(window as any).editor = editor
		;(window as any).agent = agent
		attachValidatorBridge(editor, agent)
	}, [agent, editor])

	return null
}
