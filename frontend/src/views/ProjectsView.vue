<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ChevronRight } from "lucide-vue-next";
import PageHeader from "@/components/base/PageHeader.vue";
import EmptyState from "@/components/base/EmptyState.vue";
import ProjectFormModal from "@/components/project/ProjectFormModal.vue";
import { useNavStore } from "@/stores/nav";
import type { Project } from "@/api/project";

/** 全部项目(用户直属):侧栏树的平铺视图,无上次位置时的落地页。 */
const router = useRouter();
const nav = useNavStore();

const showForm = ref(false);

onMounted(() => nav.ensureProjects(true));

function open(p: Project) {
  router.push(`/projects/${p.id}`);
}
</script>

<template>
  <div class="page">
    <PageHeader title="项目" sub="围绕研究问题组织问答;点击进入工作台,侧栏可直达每个会话">
      <template #actions>
        <button class="btn btn-primary" type="button" @click="showForm = true">新建项目</button>
      </template>
    </PageHeader>

    <div v-if="nav.loading" class="grid-kb">
      <div v-for="i in 3" :key="i" class="card skeleton-card">
        <div class="skeleton" style="height: 18px; width: 55%" />
        <div class="skeleton" style="height: 13px; width: 75%" />
      </div>
    </div>

    <EmptyState
      v-else-if="!nav.projects.length"
      title="还没有项目"
      description="项目围绕一个具体的研究问题展开,问答范围由其挂载的知识库决定。新建项目后,在项目工作台挂载知识库即可开始提问。"
    >
      <button class="btn btn-primary" type="button" @click="showForm = true">新建项目</button>
    </EmptyState>

    <div v-else class="grid-kb">
      <div
        v-for="p in nav.projects"
        :key="p.id"
        class="card card-hover proj-card"
        role="link"
        tabindex="0"
        @click="open(p)"
        @keydown.enter="open(p)"
      >
        <h3 class="proj-name">{{ p.name }}</h3>
        <p class="proj-desc">{{ p.description || "暂无描述" }}</p>
        <div class="row between proj-meta">
          <span class="created">创建于 {{ p.created_at.slice(0, 10) }}</span>
          <span class="enter">进入工作台 <ChevronRight :size="14" /></span>
        </div>
      </div>
    </div>

    <ProjectFormModal
      :open="showForm"
      @close="showForm = false"
      @saved="nav.ensureProjects(true)"
    />
  </div>
</template>

<style scoped>
.page {
  padding: var(--sp-6);
  max-width: 1200px;
  margin: 0 auto;
  width: 100%;
}

.skeleton-card {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}

.proj-card {
  cursor: pointer;
  display: flex;
  flex-direction: column;
}

.proj-name {
  margin: 0;
  font-size: var(--fs-md);
  font-weight: 600;
  color: var(--text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.proj-desc {
  margin: var(--sp-2) 0 var(--sp-4);
  flex: 1;
  font-size: var(--fs-sm);
  color: var(--text-3);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 40px;
}

.proj-meta {
  margin-top: auto;
  align-items: center;
}

.created {
  font-size: var(--fs-xs);
  color: var(--text-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.enter {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: var(--fs-xs);
  color: var(--accent);
  flex-shrink: 0;
}
</style>
