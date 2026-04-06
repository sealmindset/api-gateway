import './globals.css'
import Sidebar from '@/components/Sidebar'
import Header from '@/components/Header'

export const metadata = {
  title: 'API Gateway Admin',
  description: 'API Gateway Administration Panel',
}

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className="bg-gray-50 text-gray-900 antialiased">
        <Sidebar />
        <div className="pl-64">
          <Header />
          <main className="p-8">{children}</main>
        </div>
      </body>
    </html>
  )
}
