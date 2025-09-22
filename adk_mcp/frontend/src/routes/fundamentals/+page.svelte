<script lang="ts">
	import { onMount } from 'svelte';
	import { fundamentalsState } from '$lib/stores/fundamentals';
	import { selectedTicker } from '$lib/stores/selection';
import FundamentalsViewer from '$lib/components/FundamentalsViewer.svelte';

	$: currentTicker = $selectedTicker;
	$: fundamentals = $fundamentalsState;
	let lastSelection: string | null = null;

	$: {
		const code = currentTicker?.code ?? null;
		if (code !== lastSelection) {
			lastSelection = code;
			fundamentalsState.reset();
		}
	}

	function requestFundamentals() {
		if (!currentTicker?.code || fundamentals.status === 'loading') return;
		const code = currentTicker.code.trim();
		const site = /^[0-9]{5,6}$/.test(code) ? 'fnguide' : 'yahoofinance';
		fundamentalsState.load(site, code);
	}

	onMount(() => {
		if (currentTicker?.code) {
			requestFundamentals();
		}
	});

	$: isLoading = fundamentals.status === 'loading';
	$: hasTicker = Boolean(currentTicker?.code);
	$: actionLabel = isLoading
		? '불러오는 중...'
		: fundamentals.status === 'error'
		? '다시 시도'
		: '데이터 불러오기';
</script>

<section class="space-y-4">
	<div class="flex flex-wrap items-center gap-2">
		<button class="btn" on:click={requestFundamentals} disabled={!hasTicker || isLoading}>
			{actionLabel}
		</button>
		<span class="text-xs text-muted-foreground">
			선택: {currentTicker?.name ?? '미선택'} ({currentTicker?.code ?? '-'}) · 상태: {fundamentals.status}
		</span>
	</div>

	{#if fundamentals.status === 'idle'}
		<p class="text-sm text-muted-foreground">티커를 선택하고 데이터를 불러오세요.</p>
	{:else if fundamentals.status === 'loading'}
		<p class="text-sm text-muted-foreground">데이터를 불러오는 중입니다...</p>
	{:else if fundamentals.status === 'error'}
		<div class="rounded border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
			요청 처리 중 오류가 발생했습니다: {fundamentals.error ?? '알 수 없는 오류'}
		</div>
	{:else if fundamentals.status === 'loaded'}
		<FundamentalsViewer data={fundamentals.data ?? null} />
	{:else}
		<p class="text-sm text-muted-foreground">응답은 받았지만 표시할 데이터가 비어 있습니다.</p>
	{/if}
</section>
