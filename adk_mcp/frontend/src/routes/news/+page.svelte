<svelte:head>
	<title>뉴스 요약 · 시그노바</title>
</svelte:head>

<section class="space-y-6">
	<header class="space-y-1">
		<h1 class="text-2xl md:text-3xl font-bold tracking-tight">뉴스 요약</h1>
		<p class="text-sm text-muted-foreground">
			주요 매체의 시장 뉴스를 수집하고 요약하는 페이지입니다. FastAPI `/news` 라우터와 연결해 스트리밍 분석을 제공할 예정입니다.
		</p>
	</header>

	<div class="card space-y-3">
		<h2 class="text-lg font-semibold">향후 제공 기능</h2>
		<ul class="text-sm text-muted-foreground space-y-1">
			<li>· 뉴스 헤드라인 스트림 및 요약문</li>
			<li>· 위험/찬스 키워드 하이라이트</li>
			<li>· 종목별 뉴스 히스토리 저장 및 검색</li>
		</ul>
	</div>
</section>
