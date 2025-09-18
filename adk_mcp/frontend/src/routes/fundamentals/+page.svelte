<script lang="ts">
	import BacktestChart from '$lib/components/BacktestChart.svelte';
	import InsightCard from '$lib/components/InsightCard.svelte';
	import ScoreCard from '$lib/components/ScoreCard.svelte';
	import ScreenerPreview from '$lib/components/ScreenerPreview.svelte';
	import { fundamentalsState, type FundamentalsState } from '$lib/stores/fundamentals';
	import { selectedTicker } from '$lib/stores/selection';
	import { coreScores as fallbackScores, insights as fallbackInsights } from '$lib/stocks';

	type Insight = { summary: string; confidence: number };

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
		fundamentalsState.load('fnguide', currentTicker.code);
	}

	$: isLoading = fundamentals.status === 'loading';
	$: hasTicker = Boolean(currentTicker?.code);
	$: hasPendingTicker = hasTicker && fundamentals.ticker !== currentTicker?.code;
	$: actionLabel = isLoading
		? '불러오는 중...'
		: fundamentals.status === 'error'
		? '다시 시도'
		: hasPendingTicker
		? '데이터 불러오기'
		: '다시 불러오기';

	function parseNumber(value: unknown): number | null {
		if (typeof value === 'number' && Number.isFinite(value)) {
			return value;
		}
		if (typeof value === 'string') {
			const cleaned = value.replace(/[^0-9+\-.,]/g, '').replace(/,/g, '');
			if (!cleaned) return null;
			const parsed = Number(cleaned);
			return Number.isNaN(parsed) ? null : parsed;
		}
		return null;
	}

	function toDisplayValue(value: unknown): string {
		if (value === null || value === undefined) return '-';
		if (typeof value === 'number') return Number.isFinite(value) ? value.toLocaleString('ko-KR') : '-';
		if (typeof value === 'string') return value;
		return JSON.stringify(value);
	}

	function deriveScoreCards(state: FundamentalsState, fallback = fallbackScores) {
		if (state.status !== 'loaded' || !state.data || typeof state.data.market_conditions !== 'object') {
			return fallback;
		}
		const market = state.data.market_conditions as Record<string, unknown>;
		const mapping = [
			{ kind: '1M 수익률', key: '수익률(1M)' },
			{ kind: '3M 수익률', key: '수익률(3M)' },
			{ kind: '6M 수익률', key: '수익률(6M)' },
			{ kind: '1Y 수익률', key: '수익률(1Y)' }
		];
		return mapping.map(({ kind, key }) => {
			const raw = market[key];
			const parsed = parseNumber(raw);
			return {
				kind,
				score: parsed === null ? 50 : parsed + 50,
				delta: 0,
				displayValue: typeof raw === 'undefined' ? '-' : toDisplayValue(raw)
			};
		});
	}

	function normalizeAnalysis(raw: unknown): Record<string, unknown>[] {
		if (!raw) return [];
		if (Array.isArray(raw)) {
			return raw.filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null);
		}
		if (typeof raw === 'string') {
			try {
				const parsed = JSON.parse(raw);
				return Array.isArray(parsed)
					? parsed.filter((item: unknown): item is Record<string, unknown> => typeof item === 'object' && item !== null)
					: [];
			} catch (error) {
				console.warn('Failed to parse analysis JSON', error);
				return [];
			}
		}
		return [];
	}

	function findConfidence(row: Record<string, unknown>): number {
		const candidates = ['confidence', '신뢰도', 'score', '점수'];
		for (const key of candidates) {
			const value = row[key];
			const parsed = parseNumber(value);
			if (parsed === null) continue;
			return parsed > 1 ? Math.max(0, Math.min(1, parsed / 100)) : Math.max(0, Math.min(1, parsed));
		}
		return 0.7;
	}

	function convertAnalysisToInsights(state: FundamentalsState): Insight[] {
		if (state.status !== 'loaded' || !state.data) return [];
		const rows = normalizeAnalysis(state.data.analysis).slice(0, 3);
		return rows
			.map((row) => {
				const summary = Object.entries(row)
					.filter(([, value]) => value !== null && value !== undefined && `${value}`.trim().length > 0)
					.map(([key, value]) => `${key}: ${toDisplayValue(value)}`)
					.join(' · ');
				return summary.length > 0 ? { summary, confidence: findConfidence(row) } : null;
			})
			.filter((item): item is Insight => item !== null);
	}

	function extractMarketEntries(state: FundamentalsState, limit = 12) {
		if (state.status !== 'loaded' || !state.data) return [];
		const market = state.data.market_conditions;
		if (!market || typeof market !== 'object' || Array.isArray(market)) return [];
		return Object.entries(market as Record<string, unknown>).slice(0, limit);
	}

	function extractAnalysisRows(state: FundamentalsState) {
		if (state.status !== 'loaded' || !state.data) return [];
		return normalizeAnalysis(state.data.analysis).slice(0, 3);
	}

	$: scoreCards = deriveScoreCards(fundamentals);
	$: dynamicInsights = convertAnalysisToInsights(fundamentals);
	$: insightList = dynamicInsights.length ? dynamicInsights : fallbackInsights;
	$: marketEntries = extractMarketEntries(fundamentals);
	$: analysisRows = extractAnalysisRows(fundamentals);
</script>

<section class="space-y-6">
	<div class="space-y-1">
		<h1 class="text-2xl md:text-3xl font-bold tracking-tight">시그노바 펀더멘털 분석</h1>
		<p class="text-sm md:text-base text-muted-foreground">
			상단에서 티커 검색 후 핵심 지표와 인사이트를 확인하세요.
		</p>
		<p class="text-xs text-muted-foreground">
			현재 선택: {currentTicker?.name ?? '미선택'} ({currentTicker?.code ?? '-'}) ·
			API 상태: {fundamentals.status === 'loading' ? '불러오는 중' : fundamentals.status === 'error' ? '오류' : fundamentals.status === 'loaded' ? '완료' : '대기'}
		</p>
		<div class="flex flex-wrap items-center gap-2 pt-2">
			<button class="btn" on:click={requestFundamentals} disabled={!hasTicker || isLoading}>
				{actionLabel}
			</button>
			{#if hasPendingTicker}
				<span class="text-xs text-muted-foreground">선택한 티커의 데이터를 아직 불러오지 않았습니다.</span>
			{/if}
		</div>
	</div>

	<div class="grid grid-cols-12 gap-2 md:gap-3 lg:gap-4">
		{#each scoreCards as s}
			<div class="col-span-6 md:col-span-3">
				<ScoreCard title={s.kind} score={s.score} delta={s.delta} displayValue={s.displayValue} showMeter={false} />
			</div>
		{/each}
	</div>

	<div class="grid grid-cols-12 gap-2 md:gap-3 lg:gap-4">
		<div class="col-span-12 lg:col-span-7 flex flex-col gap-4">
			<BacktestChart />
			<div class="card">
				<div class="flex items-center justify-between">
					<h3 class="text-base font-semibold">펀더멘털 스냅샷</h3>
					{#if fundamentals.ticker}
						<span class="badge">티커 {fundamentals.ticker}</span>
					{/if}
				</div>
				{#if fundamentals.status === 'loading'}
					<p class="mt-3 text-sm text-muted-foreground">데이터를 불러오는 중입니다...</p>
				{:else if fundamentals.status === 'error'}
					<p class="mt-3 text-sm text-rose-600">{fundamentals.error ?? '알 수 없는 오류가 발생했습니다.'}</p>
				{:else if fundamentals.status === 'loaded' && fundamentals.data}
					{#if marketEntries.length}
						<dl class="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
							{#each marketEntries as [label, value]}
								<dt class="text-muted-foreground">{label}</dt>
								<dd class="font-medium">{toDisplayValue(value)}</dd>
							{/each}
						</dl>
					{:else}
						<p class="mt-3 text-sm text-muted-foreground">핵심 지표 데이터를 찾을 수 없습니다.</p>
					{/if}
					{#if analysisRows.length}
						<div class="mt-5 space-y-3">
							<h4 class="text-sm font-semibold text-muted-foreground">분석 하이라이트</h4>
							{#each analysisRows as row, idx}
								<div class="rounded-lg border border-border bg-muted/30 p-3 text-sm leading-relaxed">
									<p class="font-medium text-foreground">인사이트 {idx + 1}</p>
									<ul class="mt-2 space-y-1">
										{#each Object.entries(row) as [k, v]}
											<li><span class="text-muted-foreground">{k}</span>: {toDisplayValue(v)}</li>
										{/each}
									</ul>
								</div>
							{/each}
						</div>
					{/if}
				{:else}
					<p class="mt-3 text-sm text-muted-foreground">데이터가 준비되지 않았습니다.</p>
				{/if}
			</div>
		</div>
		<div class="col-span-12 lg:col-span-5 grid grid-rows-3 gap-2 md:gap-3">
			{#each insightList as i, idx (idx)}
				<InsightCard summary={i.summary} confidence={i.confidence} />
			{/each}
		</div>
	</div>

	<ScreenerPreview />
</section>
