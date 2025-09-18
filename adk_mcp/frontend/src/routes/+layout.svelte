<script lang="ts">
	import '../app.css';
	import Header from '$lib/components/Header.svelte';
	import Footer from '$lib/components/Footer.svelte';
	import SidebarNav from '$lib/components/SidebarNav.svelte';
	let { children } = $props();
	if (typeof document !== 'undefined') {
		const theme = localStorage.getItem('theme');
		document.documentElement.classList.toggle('dark', theme === 'dark');
	}
</script>

<div class="min-h-screen bg-gradient-to-b from-brand-50/40 to-transparent dark:from-brand-900/10">
	<Header />
	<main class="container py-4 md:py-6">
		<div class="flex flex-col gap-4 lg:grid lg:grid-cols-[240px_minmax(0,1fr)] lg:gap-6">
			<SidebarNav />
			<section class="min-h-[60vh] rounded-xl border border-transparent bg-transparent lg:border-border lg:bg-card/70">
				<div class="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6 lg:px-8">
					{@render children()}
				</div>
			</section>
		</div>
	</main>
	<Footer />
</div>
