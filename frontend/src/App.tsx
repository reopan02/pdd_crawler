import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import CookiePage from './pages/CookiePage'
import CrawlPage from './pages/CrawlPage'
import DataPage from './pages/DataPage'
import ToastContainer from './components/Toast'

export default function App() {
  return (
    <>
      <Layout>
        <Routes>
          <Route path="/" element={<Navigate to="/cookies" replace />} />
          <Route path="/cookies" element={<CookiePage />} />
          <Route path="/crawl" element={<CrawlPage />} />
          <Route path="/data" element={<DataPage />} />
        </Routes>
      </Layout>
      <ToastContainer />
    </>
  )
}
