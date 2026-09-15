import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import starlightMdTxt from 'starlight-md-txt';

export default defineConfig({
  site: 'https://pedronveloso.github.io',
  base: '/AASG',
  integrations: [
    starlight({
      title: 'AASG',
      description: 'Deterministic Android capture-to-publish pipelines.',
      favicon: '/favicon.svg',
      customCss: ['./src/styles/custom.css'],
      social: [
        { icon: 'github', label: 'GitHub', href: 'https://github.com/pedronveloso/AASG' },
      ],
      sidebar: [
        { label: 'Overview', link: '/overview/' },
        {
          label: 'Get started',
          items: [{ label: 'Quickstart', link: '/getting-started/quickstart/' }],
        },
        {
          label: 'Learn AASG',
          items: [
            { label: 'Android test contract', link: '/concepts/android-test-contract/' },
            { label: 'Capture workflow', link: '/guides/capture-workflow/' },
            { label: 'Rendering pipelines', link: '/guides/rendering/' },
            { label: 'Device frames and licensing', link: '/guides/device-frames/' },
          ],
        },
        {
          label: 'Reference',
          items: [
            { label: 'aasg.yaml schema', link: '/reference/configuration/' },
            { label: 'CLI reference', link: '/reference/cli/' },
            { label: 'Semantic metadata', link: '/reference/semantic-metadata/' },
          ],
        },
        { label: 'Contributing', link: '/contributing/' },
      ],
      plugins: [starlightMdTxt({ format: '.md.txt' })],
    }),
  ],
});
