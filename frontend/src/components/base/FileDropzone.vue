<script setup lang="ts">
import { ref } from "vue";
import { ALLOWED_EXTENSIONS, MAX_FILE_SIZE } from "@/api/document";
import { useUiStore } from "@/stores/ui";

const props = withDefaults(
  defineProps<{
    multiple?: boolean;
  }>(),
  { multiple: false }
);

const emit = defineEmits<{ files: [File[]] }>();

const ui = useUiStore();
const dragging = ref(false);
const inputEl = ref<HTMLInputElement | null>(null);

function validate(file: File): boolean {
  const ext = file.name.includes(".") ? file.name.split(".").pop()!.toLowerCase() : "";
  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    ui.toast(`不支持的文件类型:${file.name}(仅支持 ${ALLOWED_EXTENSIONS.join(" / ")})`, "error");
    return false;
  }
  if (file.size > MAX_FILE_SIZE) {
    ui.toast(`文件过大:${file.name}(上限 ${MAX_FILE_SIZE / 1024 / 1024}MB)`, "error");
    return false;
  }
  if (file.size === 0) {
    ui.toast(`文件为空:${file.name}`, "error");
    return false;
  }
  return true;
}

function accept(files: FileList | null) {
  if (!files || !files.length) return;
  const valid = Array.from(files).filter(validate);
  if (valid.length) emit("files", props.multiple ? valid : [valid[0]]);
}

function onDrop(e: DragEvent) {
  dragging.value = false;
  accept(e.dataTransfer?.files ?? null);
}

function onChange(e: Event) {
  accept((e.target as HTMLInputElement).files);
  (e.target as HTMLInputElement).value = ""; // 允许重复选择同一文件
}

function openPicker() {
  inputEl.value?.click();
}
</script>

<template>
  <div
    class="dropzone"
    :class="{ dragging }"
    role="button"
    tabindex="0"
    @click="openPicker"
    @keydown.enter.prevent="openPicker"
    @dragover.prevent="dragging = true"
    @dragleave.prevent="dragging = false"
    @drop.prevent="onDrop"
  >
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/></svg>
    <p class="dz-title">拖拽文件到此处,或点击选择</p>
    <p class="dz-hint">支持 PDF / Word / Excel / HTML / Markdown / TXT,单文件不超过 50MB{{ multiple ? ",可多选" : "" }}</p>
    <input
      ref="inputEl"
      type="file"
      hidden
      :multiple="multiple"
      :accept="ALLOWED_EXTENSIONS.map((e) => '.' + e).join(',')"
      @change="onChange"
    />
  </div>
</template>

<style scoped>
.dropzone {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--sp-1);
  padding: var(--sp-7) var(--sp-4);
  color: var(--text-3);
  border: 1.5px dashed var(--border-strong);
  border-radius: var(--r-lg);
  cursor: pointer;
  transition: border-color 0.15s ease, background-color 0.15s ease;
}

.dropzone:hover,
.dropzone.dragging {
  border-color: var(--accent);
  background: var(--accent-soft);
  color: var(--accent);
}

.dz-title {
  font-size: var(--fs-md);
  color: var(--text-2);
  margin-top: var(--sp-2);
}

.dz-hint {
  font-size: var(--fs-xs);
}
</style>
