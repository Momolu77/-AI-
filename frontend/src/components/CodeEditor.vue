<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { EditorView } from '@codemirror/view'
import { EditorState, Compartment } from '@codemirror/state'
import { html } from '@codemirror/lang-html'
import { basicSetup } from 'codemirror'
const props = defineProps<{ modelValue: string; readonly?: boolean }>()
const emit = defineEmits<{ change: [value: string, paste: boolean] }>()
const host = ref<HTMLDivElement>(),
  editable = new Compartment()
let editor: EditorView
onMounted(() => {
  editor = new EditorView({
    parent: host.value,
    state: EditorState.create({
      doc: props.modelValue,
      extensions: [
        basicSetup,
        html(),
        EditorState.allowMultipleSelections.of(false),
        editable.of(EditorState.readOnly.of(!!props.readonly)),
        EditorView.contentAttributes.of({
          'aria-label': 'HTML 代码编辑器',
          'data-testid': 'code-input',
          spellcheck: 'false',
        }),
        EditorView.theme({
          '&': { height: '100%', fontSize: '13px' },
          '.cm-scroller': { overflow: 'auto', fontFamily: 'Consolas, monospace' },
          '.cm-content': { minHeight: '100px' },
        }),
        EditorView.updateListener.of((update) => {
          if (update.docChanged && update.state.doc.toString() !== props.modelValue)
            emit(
              'change',
              update.state.doc.toString(),
              update.transactions.some((t) => t.isUserEvent('input.paste')),
            )
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
