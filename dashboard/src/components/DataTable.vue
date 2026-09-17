<template>
  <table>
    <thead>
      <tr><th v-for="col in columns" :key="col.key">{{ col.label }}</th></tr>
    </thead>
    <tbody>
      <tr v-for="(row, i) in rows" :key="i">
        <td v-for="col in columns" :key="col.key">
          <slot :name="col.key" :row="row">{{ row[col.key] ?? "—" }}</slot>
        </td>
      </tr>
      <tr v-if="!rows.length">
        <td :colspan="columns.length" class="muted" style="text-align:center">No data</td>
      </tr>
    </tbody>
  </table>
</template>

<script setup>
defineProps({
  columns: { type: Array, required: true }, // [{key, label}]
  rows: { type: Array, required: true },
});
</script>
