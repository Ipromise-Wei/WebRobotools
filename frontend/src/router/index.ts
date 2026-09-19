import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: () => import('@/views/Dashboard.vue') },
    { path: '/chassis', name: 'chassis', component: () => import('@/views/Chassis.vue') },
    { path: '/arm', name: 'arm', component: () => import('@/views/Arm.vue') },
    { path: '/gripper', name: 'gripper', component: () => import('@/views/Gripper.vue') },
    { path: '/system', name: 'system', component: () => import('@/views/System.vue') },
  ],
})

export default router

