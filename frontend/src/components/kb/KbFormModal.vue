<script setup lang="ts">
import { reactive, ref, watch } from "vue";
import Modal from "@/components/base/Modal.vue";
import { kbApi, type Kb } from "@/api/kb";
import { errMessage } from "@/api";
import { useUiStore } from "@/stores/ui";

/** 新建 / 编辑知识库(编辑时可调切片参数,仅对新索引生效)。 */
const props = defineProps<{
  open: boolean;
  kb?: Kb | null; // null = 新建
}>();

const emit = defineEmits<{
  close: [];
  saved: [kb: Kb];
}>();

const ui = useUiStore();
const saving = ref(false);

const form = reactive({
  name: "",
  description: "",
  chunk_size: "" as string | number,
  chunk_overlap: "" as string | number,
});

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    form.name = props.kb?.name ?? "";
    form.description = props.kb?.description ?? "";
    form.chunk_size = props.kb?.chunk_size ?? "";
    form.chunk_overlap = props.kb?.chunk_overlap ?? "";
  }
);

async function save() {
  if (!form.name.trim()) {
    ui.toast("请填写知识库名称", "error");
    return;
  }
  saving.value = true;
  try {
    const payload: Record<string, unknown> = {
      name: form.name.trim(),
      description: form.description.trim() || undefined,
    };
    if (form.chunk_size !== "" && form.chunk_size !== null) payload.chunk_size = Number(form.chunk_size);
    if (form.chunk_overlap !== "" && form.chunk_overlap !== null) payload.chunk_overlap = Number(form.chunk_overlap);
    const saved = props.kb
      ? await kbApi.update(props.kb.id, payload)
      : await kbApi.create(payload);
    ui.toast(props.kb ? "知识库已更新" : "知识库已创建", "success");
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
  <Modal :open="open" :title="kb ? '编辑知识库' : '新建知识库'" width="480px" @close="emit('close')">
    <div class="field">
      <label class="label" for="kb-name">名称 *</label>
      <input id="kb-name" v-model="form.name" class="input" maxlength="128" placeholder="如:Transformer 论文库" />
    </div>
    <div class="field">
      <label class="label" for="kb-desc">描述</label>
      <textarea id="kb-desc" v-model="form.description" class="textarea" rows="2" placeholder="这个知识库收录哪些资料?" />
    </div>
    <div class="row" style="gap: var(--sp-3)">
      <div class="field flex-1">
        <label class="label" for="kb-chunk">切片大小(字符,64–4096)</label>
        <input id="kb-chunk" v-model="form.chunk_size" class="input" type="number" min="64" max="4096" placeholder="默认 512" />
      </div>
      <div class="field flex-1">
        <label class="label" for="kb-overlap">切片重叠(0–1024)</label>
        <input id="kb-overlap" v-model="form.chunk_overlap" class="input" type="number" min="0" max="1024" placeholder="默认 64" />
      </div>
    </div>
    <p class="text-xs text-3">切片参数决定文档如何切分为可检索的片段,调整后仅对之后索引的文档生效。</p>
    <template #footer>
      <button class="btn btn-ghost" type="button" @click="emit('close')">取消</button>
      <button class="btn btn-primary" type="button" :disabled="saving" @click="save">
        <span v-if="saving" class="spinner" style="width: 14px; height: 14px; border-color: rgba(255,255,255,.3); border-top-color: #fff" />
        {{ saving ? "保存中…" : "保存" }}
      </button>
    </template>
  </Modal>
</template>
