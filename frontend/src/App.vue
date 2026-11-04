<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import AppLayout from "@/components/AppLayout.vue";
import ToastHost from "@/components/base/ToastHost.vue";
import ConfirmHost from "@/components/base/ConfirmHost.vue";

const route = useRoute();
const isAuthLayout = computed(() => route.meta.layout === "auth");
</script>

<template>
  <AppLayout v-if="!isAuthLayout">
    <router-view v-slot="{ Component }">
      <transition name="fade" mode="out-in">
        <component :is="Component" />
      </transition>
    </router-view>
  </AppLayout>
  <router-view v-else />
  <ToastHost />
  <ConfirmHost />
</template>
