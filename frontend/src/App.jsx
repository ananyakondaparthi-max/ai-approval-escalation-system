import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import LeaveRequest from './pages/LeaveRequest'
import MyRequests from './pages/MyRequests'

function App() {
  const token = localStorage.getItem('token')

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Login />} />
        <Route path="/dashboard" element={token ? <Dashboard /> : <Navigate to="/" />} />
        <Route path="/leave-request" element={token ? <LeaveRequest /> : <Navigate to="/" />} />
        <Route path="/my-requests" element={token ? <MyRequests /> : <Navigate to="/" />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App