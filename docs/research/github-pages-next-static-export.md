# Phase 3 deployment research

This note records the current primary-source behavior used by the Phase 3
implementation. It is pre-deployment guidance, not evidence that the public
site is live.

- Next.js static export uses `output: "export"` and writes the generated site
  to `out` during `next build`: [Next.js Static Exports](https://nextjs.org/docs/pages/guides/static-exports).
- Next.js `basePath` is a build-time setting, and `next/link` applies the
  configured prefix to internal links automatically: [Next.js basePath](https://nextjs.org/docs/pages/api-reference/config/next-config-js/basePath).
- GitHub's custom Pages workflow uses `actions/configure-pages@v5`,
  `actions/upload-pages-artifact@v4`, and `actions/deploy-pages@v4`; deployment
  needs `pages: write`, `id-token: write`, a `github-pages` environment, and a
  dependency on the build job: [Using custom workflows with GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
- The official deployment action exposes `page_url` and sets `GITHUB_PAGES` for
  Pages-aware build tools: [actions/deploy-pages](https://github.com/actions/deploy-pages).
