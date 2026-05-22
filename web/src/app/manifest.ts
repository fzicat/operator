import { MetadataRoute } from 'next'

export default function manifest(): MetadataRoute.Manifest {
    return {
        name: 'Operator',
        short_name: 'Operator',
        description: 'Trading portfolio management application',
        start_url: '/',
        display: 'standalone',
        background_color: '#282828',
        theme_color: '#282828',
        icons: [
            {
                src: '/icon-512-v4.png',
                sizes: 'any',
                type: 'image/png',
                purpose: 'maskable',
            },
        ],
    }
}
