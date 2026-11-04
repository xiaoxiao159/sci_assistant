<script setup lang="ts">
import { reactive, ref, watch } from "vue";
import Modal from "@/components/base/Modal.vue";
import { projectApi, type Project } from "@/api/project";
import { errMessage } from "@/api";
import { useUiStore } from "@/stores/ui";

const props = defineProps<{
  open: boolean;
  project?: Project | null; // null = 新建
}>();

const emit = defineEmits<{ close: []; saved: [p: Project] }>();

const ui = useUiStore();
const saving = ref(false);
const form = reactive({ name: "", description: "" });

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    form.name = props.project?.name ?? "";
    form.description = props.project?.description ?? "";
  }
);

async function save() {
  if (!form.name.trim()) return ui.toast("请填写项目名称", "error");
  saving.value = true;
  try {
    const payload = { name: form.name.trim(), description: form.description.trim() || undefined };
    const saved = props.project
      ? await projectApi.update(props.project.id, payload)
      : await projectApi.create(payload);
    ui.toast(props.project ? "项目已更新" : "项目已创建", "success");
    emit("saved", saved);
    emit("close");
  } catch (e) {
    ui.toast(errMessage(e), "error");
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <Modal :open="open" :title="project ? '编辑项目' : '新建项目'" width="460px" @close="emit('close')">
    <div class="field">
      <label class="label" for="proj-name">名称 *</label>
      <input id="proj-name" v-model="form.name" class="input" maxlength="128" placeholder="如:RAG 方法调研" />
    </div>
    <div class="field">
      <label class="label" for="proj-desc">描述</label>
      <textarea id="proj-desc" v-model="form.description" class="textarea" rows="2" placeholder="项目的研究问题或目标" />
    </div>
    <p class="text-xs text-3">项目的问答范围由它挂载的知识库决定,创建后可在项目工作台右侧管理。</p>
    <template #footer>
      <button class="btn btn-ghost" type="button" @click="emit('close')">取消</button>
      <button class="btn btn-primary" type="button" :disabled="saving" @click="save">
        {{ saving ? "保存中…" : "保存" }}
      </button>
    </template>
  </Modal>
</template>
