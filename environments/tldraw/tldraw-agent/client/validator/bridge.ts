import { Editor, TLImageExportOptions } from 'tldraw'
import { AgentHelpers } from '../../shared/AgentHelpers'
import { convertTldrawShapeToSimpleShape } from '../../shared/format/convertTldrawShapeToSimpleShape'
import { buildResponseSchema } from '../../worker/prompt/buildResponseSchema'
import { AgentAction } from '../../shared/types/AgentAction'
import { Streaming } from '../../shared/types/Streaming'
import { TldrawAgent } from '../agent/TldrawAgent'

export type ValidatorError = {
	index?: number
	message: string
	stage?: string
	actionType?: string
	shapeId?: string
	action?: AgentAction
}

export type ValidationResult = {
	errors: ValidatorError[]
	action_errors: ValidatorError[]
	simpleShapes: ReturnType<typeof convertTldrawShapeToSimpleShape>[]
	bindings: unknown[]
	rawShapesCount: number
	image?: {
		url: string
		width: number
		height: number
	}
}

export function attachValidatorBridge(editor: Editor, agent: TldrawAgent) {
	const reset = () => {
		const shapes = editor.getCurrentPageShapes()
		if (shapes.length) {
			editor.deleteShapes(shapes)
		}
		agent.reset()
	}

	const validate = async (
		actions: AgentAction[],
		imageOptions?: TLImageExportOptions | null
	): Promise<ValidationResult> => {
		const errors: ValidatorError[] = []
		const actionErrors: ValidatorError[] = []
		const helpers = new AgentHelpers(agent)

		for (let i = 0; i < actions.length; i += 1) {
			const action = actions[i]
			const { actionType, shapeId } = getActionMeta(action)
			const recordActionError = (stage: string, err: unknown, message?: string) => {
				actionErrors.push({
					index: i,
					stage,
					message: message ?? asMessage(err),
					actionType,
					shapeId,
					action,
				})
			}

			const normalizedType = actionType ?? action._type ?? action.type
			const streamingAction = {
				...action,
				_type: normalizedType,
				complete: true,
				time: 0,
			} as Streaming<AgentAction>

			let util: ReturnType<typeof agent.getAgentActionUtil>
			try {
				util = agent.getAgentActionUtil(
					normalizedType as AgentAction['_type']
				)
			} catch (err) {
				recordActionError('sanitize', err, 'Unknown action type')
				continue
			}

			let sanitized: Streaming<AgentAction> | null = null
			try {
				sanitized = util.sanitizeAction(streamingAction, helpers)
			} catch (err) {
				recordActionError('sanitize', err)
				continue
			}

			if (!sanitized) {
				recordActionError('sanitize', 'Action rejected by sanitizer', 'Action rejected by sanitizer')
				continue
			}

			let actionPromise: Promise<void> | undefined
			try {
				editor.run(
					() => {
						const { promise } = agent.act(sanitized as Streaming<AgentAction>, helpers)
						actionPromise = promise
					},
					{
						ignoreShapeLock: false,
						history: 'ignore',
					}
				)
			} catch (err) {
				recordActionError('apply', err)
				continue
			}

			if (actionPromise) {
				try {
					await actionPromise
				} catch (err) {
					recordActionError('await', err)
				}
			}
		}

		await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))

		const shapes = editor.getCurrentPageShapesSorted()
		const simpleShapes = [] as ReturnType<typeof convertTldrawShapeToSimpleShape>[]

		for (const shape of shapes) {
			try {
				simpleShapes.push(convertTldrawShapeToSimpleShape(editor, shape))
			} catch (err) {
				errors.push({
					stage: 'shape_convert',
					shapeId: shape.id,
					message: asMessage(err),
				})
			}
		}

		const bindings = editor.store.query.records('binding').get()
		let image: ValidationResult['image']

		if (imageOptions) {
			const shapeIds = Array.from(editor.getCurrentPageShapeIds())
			try {
				if (shapeIds.length === 0) {
					errors.push({
						stage: 'export',
						message: 'Image export failed: no shapes on canvas',
					})
				} else {
					await editor.fonts.loadRequiredFontsForCurrentPage(
						editor.options.maxFontsToLoadBeforeRender
					)
				}
				const { blob, width, height } = await editor.toImage(shapeIds, imageOptions)
				const url = await blobToDataUrl(blob)
				image = { url, width, height }
			} catch (err) {
				errors.push({ stage: 'export', message: `Image export failed: ${asMessage(err)}` })
			}
		}

		return {
			errors,
			action_errors: actionErrors,
			simpleShapes,
			bindings,
			rawShapesCount: shapes.length,
			image,
		}
	}

	const getResponseSchema = () => buildResponseSchema()

	;(window as any).__tldrawValidator = {
		reset,
		validate,
		getResponseSchema,
	}
}

function asMessage(err: unknown) {
	if (err instanceof Error) return err.message
	return typeof err === 'string' ? err : JSON.stringify(err)
}

function getActionMeta(action: AgentAction) {
	const actionType = (action as any)._type ?? (action as any).type
	const shapeId =
		(action as any).shapeId ??
		(action as any).props?.shapeId ??
		(action as any).shape?.id ??
		(action as any).props?.id
	return { actionType, shapeId }
}

function blobToDataUrl(blob: Blob): Promise<string> {
	return new Promise((resolve, reject) => {
		const reader = new FileReader()
		reader.onload = () => resolve(String(reader.result))
		reader.onerror = () => reject(reader.error ?? new Error('Failed to read image blob'))
		reader.readAsDataURL(blob)
	})
}
