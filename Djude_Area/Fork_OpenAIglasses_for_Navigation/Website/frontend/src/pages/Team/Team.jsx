import { useState, useEffect } from 'react'
import { fetchTeamMembers } from '../../api/client'
import { useContent } from '../../context/ContentContext'
import ScrollReveal from '../../components/ScrollReveal'
import { motion } from 'framer-motion'
import { MemberCardSkeleton } from '../../components/Skeleton'

function MemberCard({ member }) {
  return (
    <motion.div
      whileHover={{ y: -4 }}
      transition={{ duration: 0.2 }}
      className="glass gradient-top-border rounded-2xl p-6 hover:glow-border transition-all duration-300 group"
    >
      {/* 頭像 */}
      <div className="mb-4">
        {member.avatar ? (
          <img
            src={member.avatar}
            alt={member.name}
            className="w-20 h-20 rounded-2xl object-cover mx-auto"
          />
        ) : (
          <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-warm-600 to-warm-800 dark:from-brand-700 dark:to-brand-900 flex items-center justify-center text-3xl font-bold text-warm-200 dark:text-brand-300 mx-auto">
            {member.name.charAt(0)}
          </div>
        )}
      </div>

      {/* 資訊 */}
      <div className="text-center">
        <h3 className="font-semibold text-gray-900 dark:text-white text-lg group-hover:text-warm-600 dark:group-hover:text-brand-400 transition-colors">
          {member.name}
        </h3>
        <p className="text-warm-600 dark:text-brand-400 text-sm mt-1 mb-3">{member.role}</p>
        {member.bio && (
          <p className="text-gray-700 dark:text-gray-400 text-xs leading-relaxed line-clamp-3">{member.bio}</p>
        )}
      </div>

      {/* 社群連結 */}
      <div className="flex items-center justify-center gap-3 mt-4">
        {member.github_url && (
          <a
            href={member.github_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors"
            title="GitHub"
          >
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
            </svg>
          </a>
        )}
        {member.linkedin_url && (
          <a
            href={member.linkedin_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-gray-600 dark:text-gray-400 hover:text-blue-400 transition-colors"
            title="LinkedIn"
          >
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
            </svg>
          </a>
        )}
        {member.email && (
          <a
            href={`mailto:${member.email}`}
            className="text-gray-600 dark:text-gray-400 hover:text-warm-600 dark:hover:text-brand-400 transition-colors"
            title="Email"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
          </a>
        )}
      </div>
    </motion.div>
  )
}

export default function Team() {
  const [members, setMembers] = useState([])
  const [loading, setLoading] = useState(true)
  const { team: c } = useContent()

  useEffect(() => {
    fetchTeamMembers()
      .then((res) => {
        const data = res.data.results || res.data
        setMembers(data)
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const referenceMembers = members.filter((m) => m.member_type === 'reference')
  const developerMembers = members.filter((m) => m.member_type === 'developer')

  if (loading) {
    return (
      <div className="pt-24 pb-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <div className="animate-pulse bg-gray-200 dark:bg-gray-700 rounded h-10 w-48 mx-auto mb-4" />
            <div className="animate-pulse bg-gray-200 dark:bg-gray-700 rounded h-5 w-96 max-w-full mx-auto" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {[0, 1, 2, 3].map(i => <MemberCardSkeleton key={i} />)}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="pt-24 pb-20">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <ScrollReveal>
          <h1 className="section-title">{c.page_title || '關於團隊'}</h1>
          <p className="section-subtitle">
            {c.subtitle || '本專案結合開源社群的創意與我們開發團隊的技術，共同打造 AI 智慧眼鏡的未來。'}
          </p>
        </ScrollReveal>

        {/* 原專案參考者 */}
        {referenceMembers.length > 0 && (
          <section className="mb-16">
            <ScrollReveal>
              <div className="flex items-center gap-4 mb-8">
                <div className="h-px flex-1 bg-gradient-to-r from-transparent via-warm-500/50 dark:via-brand-500/50 to-transparent opacity-70" />
                <h2 className="text-xl font-semibold text-warm-600 dark:text-brand-400 whitespace-nowrap px-4">
                  {c.reference_title || '原專案參考者'}
                </h2>
                <div className="h-px flex-1 bg-gradient-to-r from-transparent via-warm-500/50 dark:via-brand-500/50 to-transparent opacity-70" />
              </div>
              <p className="text-center text-gray-700 text-sm mb-8">
                {c.reference_description || '感謝以下開源貢獻者的創作，本專案基於'}{' '}
                <a
                  href={c.reference_link_url || 'https://github.com/AI-FanGe/OpenAIglasses_for_Navigation'}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-warm-600 dark:text-brand-400 hover:underline"
                >
                  {c.reference_link_text || 'OpenAIglasses_for_Navigation'}
                </a>
              </p>
            </ScrollReveal>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 max-w-3xl mx-auto">
              {referenceMembers.map((member, i) => (
                <ScrollReveal key={member.id} delay={i * 0.1}>
                  <MemberCard member={member} />
                </ScrollReveal>
              ))}
            </div>
          </section>
        )}

        {/* 開發團隊 */}
        {developerMembers.length > 0 && (
          <section>
            <ScrollReveal>
              <div className="flex items-center gap-4 mb-8">
                <div className="h-px flex-1 bg-gradient-to-r from-transparent via-gray-400/50 dark:via-white/20 to-transparent opacity-70" />
                <h2 className="text-xl font-semibold text-gray-900 dark:text-white whitespace-nowrap px-4">
                  {c.developer_title || '我們的開發團隊'}
                </h2>
                <div className="h-px flex-1 bg-gradient-to-r from-transparent via-gray-400/50 dark:via-white/20 to-transparent opacity-70" />
              </div>
            </ScrollReveal>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
              {developerMembers.map((member, i) => (
                <ScrollReveal key={member.id} delay={i * 0.08}>
                  <MemberCard member={member} />
                </ScrollReveal>
              ))}
            </div>
          </section>
        )}

        {members.length === 0 && (
          <div className="text-center text-gray-700 dark:text-gray-400 py-20">
            {c.empty_message || '團隊成員資料載入中，或請至後台管理介面新增成員。'}
          </div>
        )}
      </div>
    </div>
  )
}
