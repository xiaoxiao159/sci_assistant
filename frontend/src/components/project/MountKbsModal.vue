<script setup lang="ts">
import { ref, watch } from "vue";
import Modal from "@/components/base/Modal.vue";
import { projectApi, type MountedKb } from "@/api/project";
import { kbApi, type Kb } from "@/api/kb";
import { errMessage } from "@/api";
import { useUiStore } from "@/stores/ui";

/** 管理项目挂载的知识库(检索范围)。挂载/解除即时生效。 */
const props = defineProps<{
  open: boolean;
  projectId: string;
}>();

const emit = defineEmits<{ close: []; changed: [] }>();

const ui = useUiStore();
const loading = ref(true);
const allKbs = ref<Kb[]>([]);
const mountedIds = ref<Set<string>>(new Set());
const mountedInfo = ref<Record<string, MountedKb>>({});
const busyId = ref<string | null>(null);

watch(
  () => props.open,
  async (open) => {
    if (!open) return;
    loading.value = true;
    try {
      const [kbs, mounted] = await Promise.all([
        kbApi.list(),
        projectApi.listMountedKbs(props.projectId),
      ]);
      allKbs.value = kbs;
      mountedInfo.value = Object.fromEntries(mounted.map((m) => [m.knowledge_base_id, m]));
      mountedIds.value = new Set(mounted.map((m) => m.knowledge_base_id));
    } catch (e) {
      ui.toast(errMessage(e), "error");
    } finally {
      loading.value = false;
    }
  }
);

async function toggle(kb: Kb) {
  busyId.value = kb.id;
  try {
    if (mountedIds.value.has(kb.id)) {
      await projectApi.unmountKb(props.projectId, kb.id);
      const next = new Set(mountedIds.value);
      next.delete(kb.id);
      mountedIds.value = next;
      ui.toast(`已解除「${kb.name}」`, "info");
    } else {
      await projectApi.mountKb(props.projectId, kb.id);
      const next = new Set(mountedIds.value);
      next.add(kb.id);
      mountedIds.value = next;
      ui.toast(`已挂载「${kb.name}」`, "success");
    }
    emit("changed");
  } catch (e) {
    ui.toast(errMessage(e), "error");
  } finally {
    busyId.value = null;
  }
}
</script>

<template>
  <Modal :open="open" title="管理挂载的知识库" width="560px" @close="emit('close')">
    <p class="text-sm text-2 mb-4">勾选的知识库将参与本项目的检索问答;只能挂载你自己名下、启用中的知识库。</p>
    <div v-if="loading" class="col">
      <div class="skeleton" style="height: 40px" />
      <div class="skeleton" style="height: 40px" />
      <div class="skeleton" style="height: 40px" />
    </div>
    <template v-else>
      <div v-if="!allKbs.length" class="text-3 text-sm" style="padding: var(--sp-4)">
        还没有知识库。先到「知识库」页创建并上传文档,再回来挂载。
      </div>
      <div v-else class="kb-options">
        <label
          v-for="kb in allKbs"
          :key="kb.id"
          class="kb-option"
          :class="{ checked: mountedIds.has(kb.id), disabled: kb.status !== 'active' }"
        >
          <input
            type="checkbox"
            :checked="mountedIds.has(kb.id)"
            :disabled="kb.status !== 'active' || busyId === kb.id"
            @change="toggle(kb)"
          />
          <div class="flex-1">
            <div class="row">
              <span class="kb-name">{{ kb.name }}</span>
              <span v-if="kb.status !== 'active'" class="tag">已归档</span>
            </div>
            <div class="text-xs text-3">{{ kb.doc_count }} 篇文档{{ kb.description ? " · " + kb.description : "" }}</div>
          </div>
          <span v-if="busyId === kb.id" class="spinner" style="width: 14px; height: 14px" />
        </label>
      </div>
    </template>
  </Modal>
</template>

<style scoped>
.kb-options {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}

.kb-option {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  cursor: pointer;
}

.kb-option:hover:not(.disabled) {
  border-color: var(--border-strong);
}

.kb-option.checked {
  border-color: var(--accent);
  background: var(--accent-soft);
}

.kb-option.disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.kb-option input {
  width: 16px;
  height: 16px;
  accent-color: var(--accent);
}

.kb-name {
  font-weight: 500;
}
</style>
