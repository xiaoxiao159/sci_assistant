<script setup lang="ts">
import { ref } from "vue";
import Modal from "@/components/base/Modal.vue";
import FileDropzone from "@/components/base/FileDropzone.vue";
import StatusBadge from "@/components/base/StatusBadge.vue";
import { documentApi, type UploadResult } from "@/api/document";
import { errMessage } from "@/api";
import { useUiStore } from "@/stores/ui";

const props = defineProps<{
  open: boolean;
  kbId: string;
}>();

const emit = defineEmits<{ close: []; uploaded: [] }>();

const ui = useUiStore();
const uploading = ref(false);
const results = ref<{ name: string; res: UploadResult | null; error?: string }[]>([]);

async function onFiles(files: File[]) {
  uploading.value = true;
  for (const f of files) {
    const item = { name: f.name, res: null as UploadResult | null, error: undefined as string | undefined };
    results.value.push(item);
    try {
      item.res = await documentApi.upload(props.kbId, f);
      if (item.res.is_dedup) ui.toast(`「${f.name}」内容未变化,已复用现有版本`, "info");
    } catch (e) {
      item.error = errMessage(e);
    }
  }
  uploading.value = false;
  emit("uploaded");
}

function reset() {
  results.value = [];
}
</script>

<template>
  <Modal :open="open" title="上传文档" width="560px" @close="emit('close'); reset()">
    <FileDropzone multiple @files="onFiles" />
    <div v-if="results.length" class="mt-4 upload-results">
      <div v-for="r in results" :key="r.name" class="upload-row">
        <span class="upload-name" :title="r.name">{{ r.name }}</span>
        <template v-if="r.res">
          <StatusBadge :status="r.res.status" kind="document" />
          <span v-if="r.res.is_dedup" class="tag">内容去重</span>
        </template>
        <template v-else-if="r.error">
          <span class="text-xs" style="color: var(--danger)">{{ r.error }}</span>
        </template>
        <span v-else class="spinner" style="width: 14px; height: 14px" />
      </div>
      <p class="text-xs text-3 mt-2">上传完成后解析与索引在后台进行,可稍后在列表查看状态,或到任务中心跟踪。</p>
    </div>
  </Modal>
</template>

<style scoped>
.upload-results {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}

.upload-row {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: var(--fs-sm);
}

.upload-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
