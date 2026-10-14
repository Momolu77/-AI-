<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { EditorView } from '@codemirror/view'
import { EditorState, Compartment } from '@codemirror/state'
import { html } from '@codemirror/lang-html'
import { verifyPaste, type CopyClaim } from '../services/copy'
import type { EditChange } from '../types'
import { basicSetup } from 'codemirror'
const props = defineProps<{ modelValue: string; readonly?: boolean }>()
const emit = defineEmits<{
  change: [value: string, paste: boolean, changes: EditChange[], pasteClaim: CopyClaim | null]
}>()
const host = ref<HTMLDivElement>(),
  editable = new Compartment()
let editor: EditorView
let pasteClaim: CopyClaim | null = null
onMounted(() => {
  editor = new EditorView({
    parent: host.value,
    state: EditorState.create({
      doc: props.modelValue,
      extensions: [
        basicSetup,
        EditorView.domEventHandlers({
          paste: (event) => {
            pasteClaim = verifyPaste(event)
            return false
          },
        }),
        html(),
        EditorState.allowMultipleSelections.of(false),
        editable.of(EditorState.readOnly.of(!!props.readonly)),
        EditorView.contentAttributes.of({
          'aria-label': 'HTML 代码编辑器',
          'data-testid': 'code-input',
          spellcheck: 'false',
        }),
        EditorView.theme({
          '&': { height: '100%', fontSize: 'var(--ui-font-body)' },
          '.cm-scroller': { overflow: 'auto', fontFamily: 'var(--ui-font-mono)' },
          '.cm-content': { minHeight: '100px', padding: '12px 0', lineHeight: '1.65' },
          '.cm-line': { padding: '0 12px' },
        }),
        EditorView.updateListener.of((update) => {
          if (!update.docChanged || update.state.doc.toString() === props.modelValue) return
          for (const transaction of update.transactions) {
            if (!transaction.docChanged) continue
            const changes: EditChange[] = []
            let shift = 0
            transaction.changes.iterChanges((from, to, _fromB, _toB, inserted) => {
              const inserted_text = inserted.toString(),
                deleted_text = transaction.startState.doc.sliceString(from, to)
              changes.push({
                operation: transaction.isUserEvent('undo')
                  ? 'undo'
                  : transaction.isUserEvent('redo')
                    ? 'redo'
                    : inserted_text
                      ? deleted_text
                        ? 'replace'
                        : 'insert'
                      : 'delete',
                inserted_text,
                deleted_text,
                edit_range: { start: from + shift, end: to + shift },
                base_revision: 0,
                result_revision: 1,
              })
              shift += inserted.length - (to - from)
            })
            emit(
              'change',
              transaction.newDoc.toString(),
              transaction.isUserEvent('input.paste'),
              changes,
              transaction.isUserEvent('input.paste') ? pasteClaim : null,
            )
            pasteClaim = null
          }
        }),
      ],
    }),
  })
})
watch(
  () => props.modelValue,
  (value) => {
    if (editor && value !== editor.state.doc.toString())
      editor.dispatch({ changes: { from: 0, to: editor.state.doc.length, insert: value } })
  },
)
watch(
  () => props.readonly,
  (value) => editor?.dispatch({ effects: editable.reconfigure(EditorState.readOnly.of(!!value)) }),
)
onBeforeUnmount(() => editor?.destroy())
</script>
<template><div ref="host" class="code-editor"></div></template>
