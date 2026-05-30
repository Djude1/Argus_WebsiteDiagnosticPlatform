import { createContext, useContext, useState, useEffect } from 'react'
import { fetchContent } from '../api/client'

const ContentContext = createContext({})

export function ContentProvider({ children }) {
  const [content, setContent] = useState({
    site: {}, home: {}, product: {}, download: {}, purchase: {}, team: {},
  })

  useEffect(() => {
    fetchContent()
      .then((res) => setContent(res.data))
      .catch(console.error)
  }, [])

  return (
    <ContentContext.Provider value={content}>
      {children}
    </ContentContext.Provider>
  )
}

export const useContent = () => useContext(ContentContext)
