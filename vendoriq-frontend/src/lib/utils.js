export const formatCurrency = (amount) => {
  const num = Number(amount) || 0
  return new Intl.NumberFormat('en-NG', {
    style: 'currency', currency: 'NGN',
    minimumFractionDigits: 0, maximumFractionDigits: 0,
  }).format(num)
}

export const formatNumber = (num) =>
  new Intl.NumberFormat('en-NG').format(Number(num) || 0)

export const formatDate = (date) =>
  new Date(date).toLocaleDateString('en-NG', { day: 'numeric', month: 'short', year: 'numeric' })

export const formatTime = (date) =>
  new Date(date).toLocaleTimeString('en-NG', { hour: '2-digit', minute: '2-digit' })

export const formatDateTime = (date) => `${formatDate(date)}, ${formatTime(date)}`

export const getErrorMessage = (err) =>
  err?.response?.data?.error || err?.response?.data?.message || err?.message || 'Something went wrong'
