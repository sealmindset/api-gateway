import './globals.css'
import { ThemeProvider } from '@/components/theme-provider'
import Sidebar from '@/components/Sidebar'
import Header from '@/components/Header'

export const metadata = {
  title: 'API Gateway Admin',
  description: 'API Gateway Administration Panel',
}

export default function RootLayout({ children }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen font-sans antialiased" suppressHydrationWarning>
        <ThemeProvider>
          <div className="flex h-screen overflow-hidden">
            <Sidebar />
            <div className="flex flex-1 flex-col overflow-hidden">
              <Header />
              <main className="flex-1 overflow-y-auto p-6">{children}</main>
            </div>
          </div>
        </ThemeProvider>
      </body>
    </html>
  )
}
