<svelte:head>
	<title>사유존</title>
</svelte:head>

<section class="space-y-8">
	<div class="space-y-2">
		<h1 class="text-3xl font-bold tracking-tight">사이트 요약</h1>
		<p class="text-muted-foreground">
			좌측 네비게이션을 통해 펀더멘털, 시장, 뉴스 분석 페이지로 이동할 수 있습니다. 원하는 섹션을
			선택해 상세 데이터를 불러오세요.
		</p>
	</div>

	<div class="grid gap-6 md:grid-cols-2">
		<article class="card">
			<h2 class="text-xl font-semibold">펀더멘털 분석</h2>
			<p class="text-muted-foreground mt-2 text-sm">
				국내 주요 종목의 재무 지표와 AI 분석 리포트를 확인합니다. 종목을 선택한 뒤 데이터를 직접
				불러올 수 있습니다.
			</p>
			<a class="btn mt-4 inline-flex" href="/fundamentals">바로 가기</a>
		</article>

		<article class="card">
			<h2 class="text-xl font-semibold">시장 데이터 스트리밍</h2>
			<p class="text-muted-foreground mt-2 text-sm">
				실시간 SSE 기반으로 수집되는 시장 이벤트와 AI 해석을 제공할 예정입니다. 알파 버전 준비
				중입니다.
			</p>
			<a class="btn mt-4 inline-flex" href="/market">바로 가기</a>
		</article>

		<article class="card">
			<h2 class="text-xl font-semibold">뉴스 요약</h2>
			<p class="text-muted-foreground mt-2 text-sm">
				언론 보도와 주요 이슈를 수집·정제해 요약을 제공하는 뉴스 분석 페이지입니다. 현재 베타
				테스트를 준비하고 있습니다.
			</p>
			<a class="btn mt-4 inline-flex" href="/news">바로 가기</a>
		</article>

		<article class="card">
			<h2 class="text-xl font-semibold">사용 가이드</h2>
			<p class="text-muted-foreground mt-2 text-sm">
				좌측 사이드바에서 분석 유형을 선택해 데이터를 불러오고, 상단 검색창에서 종목을 검색해 세부
				분석을 진행하세요.
			</p>
		</article>
	</div>
</section>
