<svelte:head>
	<title>시장 데이터 스트리밍 · 시그노바</title>
</svelte:head>

<section class="space-y-6">
	<header class="space-y-1">
		<h1 class="text-2xl md:text-3xl font-bold tracking-tight">시장 데이터 스트리밍</h1>
		<p class="text-sm text-muted-foreground">
			SSE 기반으로 시장 데이터 수집 및 AI 분석을 제공할 예정입니다. 준비가 완료되면 이 화면에서 실시간 이벤트를 확인할 수 있습니다.
		</p>
	</header>

	<div class="card space-y-3">
		<h2 class="text-lg font-semibold">진행 상황</h2>
		<ul class="text-sm text-muted-foreground space-y-1">
			<li>· FastAPI `/market` 라우터와 연동한 SSE UI 설계 중</li>
			<li>· 종가/거래량, AI 요약 패널, 진행 로그 컴포넌트 개발 예정</li>
			<li>· 완성 전까지는 샘플 이벤트 데이터를 제공할 계획입니다.</li>
		</ul>
	</div>
</section>
