<script lang="ts">
	import { onMount } from 'svelte';
	import { fundamentalsState } from '$lib/stores/fundamentals';
	import { selectedTicker } from '$lib/stores/selection';
	import FundamentalsViewer from '$lib/components/FundamentalsViewer.svelte';

	let currentTicker = $derived($selectedTicker);
	let fundamentals = $derived($fundamentalsState);
	let lastSelection = $state<string | null>(null);

	$effect(() => {
		const code = currentTicker?.code ?? null;
		if (code !== lastSelection) {
			lastSelection = code;
			fundamentalsState.reset();
		}
	});

	function requestFundamentals() {
		if (!currentTicker?.code || fundamentals.status === 'loading') return;
		const ticker = currentTicker.code.trim();
		fundamentalsState.load(ticker);
	}

	onMount(() => {
		if (currentTicker?.code) {
			requestFundamentals();
		}
	});

	let isLoading = $derived(fundamentals.status === 'loading');
	let hasTicker = $derived(Boolean(currentTicker?.code));
	let actionLabel = $derived(
		isLoading ? '불러오는 중...' : fundamentals.status === 'error' ? '다시 시도' : '데이터 불러오기'
	);
</script>

<section class="space-y-4">
	<div class="flex flex-wrap items-center gap-2">
		<button class="btn" onclick={requestFundamentals} disabled={!hasTicker || isLoading}>
			{actionLabel}
		</button>
		<span class="text-muted-foreground text-xs">
			선택: {currentTicker?.name ?? '미선택'} ({currentTicker?.code ?? '-'}) · 상태: {fundamentals.status}
		</span>
	</div>

	{#if fundamentals.status === 'idle'}
		<p class="text-muted-foreground text-sm">티커를 선택하고 데이터를 불러오세요.</p>
	{:else if fundamentals.status === 'loading'}
		<p class="text-muted-foreground text-sm">데이터를 불러오는 중입니다...</p>
	{:else if fundamentals.status === 'error'}
		<div class="rounded border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
			요청 처리 중 오류가 발생했습니다: {fundamentals.error ?? '알 수 없는 오류'}
		</div>
	{:else if fundamentals.status === 'loaded'}
		<FundamentalsViewer data={fundamentals.data ?? null} />
	{:else}
		<p class="text-muted-foreground text-sm">응답은 받았지만 표시할 데이터가 비어 있습니다.</p>
	{/if}
</section>
