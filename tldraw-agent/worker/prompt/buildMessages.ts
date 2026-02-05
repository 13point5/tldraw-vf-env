import { ModelMessage, UserContent } from 'ai'
import { getPromptPartUtilsRecord } from '../../shared/AgentUtils'
import { AgentMessage } from '../../shared/types/AgentMessage'
import { AgentPrompt } from '../../shared/types/AgentPrompt'
import { AgentModelName, getAgentModelDefinition } from '../models'

export function buildMessages(prompt: AgentPrompt, modelName: AgentModelName): ModelMessage[] {
	const utils = getPromptPartUtilsRecord()
	let allMessages: AgentMessage[] = []

	// Get model definition to check image support
	const modelDefinition = getAgentModelDefinition(modelName)
	const supportsImages = modelDefinition.supportsImages !== false // default true

	for (const part of Object.values(prompt)) {
		const util = utils[part.type]
		const messages = util.buildMessages(part)
		allMessages.push(...messages)
	}

	// Filter out entire messages that contain images if model doesn't support them
	if (!supportsImages) {
		allMessages = allMessages.filter(
			(msg) => !msg.content.some((item) => item.type === 'image')
		)
	}

	allMessages.sort((a, b) => b.priority - a.priority)

	return toModelMessages(allMessages)
}

/**
 * Convert AgentMessage[] to ModelMessage[] for the AI SDK
 */
function toModelMessages(agentMessages: AgentMessage[]): ModelMessage[] {
	return agentMessages.map((tlMessage) => {
		const content: UserContent = []

		for (const contentItem of tlMessage.content) {
			if (contentItem.type === 'image') {
				content.push({
					type: 'image',
					image: contentItem.image!,
				})
			} else {
				content.push({
					type: 'text',
					text: contentItem.text!,
				})
			}
		}

		return {
			role: tlMessage.role,
			content,
		} as ModelMessage
	})
}
