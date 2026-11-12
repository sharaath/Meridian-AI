import React, { useState } from 'react';
import {
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  useWindowDimensions,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { usePathname, useRouter } from 'expo-router';
import { MeridianLogo } from '@/components/MeridianLogo';
import { useAuth } from '@/contexts/AuthContext';
import { useChat } from '@/contexts/ChatContext';
import { useTheme } from '@/contexts/ThemeContext';
import { api } from '@/services/api';

export function SidebarShell({ children }: { children: React.ReactNode }) {
  const { width } = useWindowDimensions();
  const isDesktop = width >= 900;
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameText, setRenameText] = useState('');
  const [projectModalOpen, setProjectModalOpen] = useState(false);
  const [newProjName, setNewProjName] = useState('');
  const [newProjInstructions, setNewProjInstructions] = useState('');

  const { palette, isDark, toggleTheme } = useTheme();
  const { user, logout } = useAuth();
  const {
    conversations,
    projects,
    selectedProjectId,
    searchQuery,
    setSelectedProjectId,
    setSearchQuery,
    refreshSidebar,
  } = useChat();

  const router = useRouter();
  const pathname = usePathname();

  const navigate = (path: string) => {
    setDrawerOpen(false);
    router.push(path as never);
  };

  const handleRenameSubmit = async (convId: string) => {
    if (!renameText.trim()) {
      setRenamingId(null);
      return;
    }
    try {
      await api.updateConversation(convId, { title: renameText.trim() });
      await refreshSidebar();
    } finally {
      setRenamingId(null);
    }
  };

  const handleDeleteConv = async (convId: string) => {
    await api.deleteConversation(convId);
    await refreshSidebar();
    if (pathname === `/chat/${convId}`) {
      router.replace('/chat' as never);
    }
  };

  const handleCreateProject = async () => {
    if (!newProjName.trim()) return;
    await api.createProject({
      name: newProjName.trim(),
      custom_instructions: newProjInstructions.trim(),
    });
    setNewProjName('');
    setNewProjInstructions('');
    setProjectModalOpen(false);
    await refreshSidebar();
  };

  const navItems: Array<{ label: string; path: string; icon: keyof typeof Ionicons.glyphMap; adminOnly?: boolean }> = [
    { label: 'Documents', path: '/documents', icon: 'document-text-outline' },
    { label: 'Memory', path: '/memory', icon: 'bookmark-outline' },
    { label: 'Models', path: '/models', icon: 'hardware-chip-outline' },
    { label: 'Usage', path: '/usage', icon: 'stats-chart-outline' },
    { label: 'Settings', path: '/settings', icon: 'settings-outline' },
    { label: 'Profile', path: '/profile', icon: 'person-circle-outline' },
    { label: 'Admin', path: '/admin', icon: 'shield-checkmark-outline', adminOnly: true },
  ];

  const renderSidebarContent = () => (
    <View style={[styles.sidebarInner, { backgroundColor: palette.sidebar, borderRightColor: palette.border }]}>
      <View style={styles.sidebarHeader}>
        <TouchableOpacity onPress={() => navigate('/chat')}>
          <MeridianLogo size={30} />
        </TouchableOpacity>
        <View style={{ flexDirection: 'row', gap: 6 }}>
          <TouchableOpacity onPress={toggleTheme} style={[styles.iconBtn, { borderColor: palette.border }]}>
            <Ionicons name={isDark ? 'sunny-outline' : 'moon-outline'} size={17} color={palette.textSecondary} />
          </TouchableOpacity>
          {isDesktop ? (
            <TouchableOpacity onPress={() => setSidebarCollapsed(true)} style={[styles.iconBtn, { borderColor: palette.border }]}>
              <Ionicons name="chevron-back" size={17} color={palette.textSecondary} />
            </TouchableOpacity>
          ) : null}
        </View>
      </View>

      <TouchableOpacity
        onPress={() => navigate('/chat')}
        style={[styles.newChatBtn, { backgroundColor: palette.accent }]}
      >
        <Ionicons name="add" size={18} color="#FFFFFF" />
        <Text style={styles.newChatText}>New chat</Text>
      </TouchableOpacity>

      <View style={[styles.searchBox, { backgroundColor: palette.surface, borderColor: palette.border }]}>
        <Ionicons name="search-outline" size={15} color={palette.textMuted} />
        <TextInput
          value={searchQuery}
          onChangeText={setSearchQuery}
          placeholder="Search chats..."
          placeholderTextColor={palette.textMuted}
          style={[styles.searchInput, { color: palette.text }]}
        />
        {searchQuery ? (
          <TouchableOpacity onPress={() => setSearchQuery('')}>
            <Ionicons name="close-circle" size={15} color={palette.textMuted} />
          </TouchableOpacity>
        ) : null}
      </View>

      <ScrollView style={{ flex: 1 }} showsVerticalScrollIndicator={false}>
        {/* Projects */}
        <View style={styles.sectionHeader}>
          <Text style={[styles.sectionLabel, { color: palette.textMuted }]}>PROJECTS</Text>
          <TouchableOpacity onPress={() => setProjectModalOpen(true)}>
            <Ionicons name="add-circle-outline" size={16} color={palette.accent} />
          </TouchableOpacity>
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 10 }}>
          <View style={{ flexDirection: 'row', gap: 6, paddingHorizontal: 2 }}>
            <TouchableOpacity
              onPress={() => setSelectedProjectId(null)}
              style={[
                styles.projectPill,
                {
                  backgroundColor: selectedProjectId === null ? palette.accentSoft : palette.surface,
                  borderColor: selectedProjectId === null ? palette.accent : palette.border,
                },
              ]}
            >
              <Text style={{ fontSize: 12, fontWeight: '600', color: selectedProjectId === null ? palette.accent : palette.textSecondary }}>
                All
              </Text>
            </TouchableOpacity>
            {projects.map((p) => {
              const active = selectedProjectId === p.id;
              return (
                <TouchableOpacity
                  key={p.id}
                  onPress={() => setSelectedProjectId(active ? null : p.id)}
                  style={[
                    styles.projectPill,
                    {
                      backgroundColor: active ? palette.accentSoft : palette.surface,
                      borderColor: active ? palette.accent : palette.border,
                    },
                  ]}
                >
                  <Text style={{ fontSize: 12, fontWeight: '600', color: active ? palette.accent : palette.textSecondary }}>
                    {p.name}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </ScrollView>

        {/* Conversations */}
        <Text style={[styles.sectionLabel, { color: palette.textMuted, marginBottom: 6 }]}>RECENT CHATS</Text>
        {conversations.length === 0 ? (
          <Text style={{ fontSize: 12.5, color: palette.textMuted, paddingVertical: 8 }}>
            No conversations yet. Start a new chat above.
          </Text>
        ) : (
          conversations.map((conv) => {
            const active = pathname === `/chat/${conv.id}`;
            return (
              <View
                key={conv.id}
                style={[
                  styles.convRow,
                  {
                    backgroundColor: active ? palette.surfaceElevated : 'transparent',
                    borderColor: active ? palette.border : 'transparent',
                  },
                ]}
              >
                {renamingId === conv.id ? (
                  <TextInput
                    value={renameText}
                    onChangeText={setRenameText}
                    autoFocus
                    onSubmitEditing={() => handleRenameSubmit(conv.id)}
                    onBlur={() => handleRenameSubmit(conv.id)}
                    style={[styles.renameInput, { color: palette.text, borderColor: palette.accent }]}
                  />
                ) : (
                  <TouchableOpacity
                    style={{ flex: 1, paddingVertical: 6 }}
                    onPress={() => navigate(`/chat/${conv.id}`)}
                  >
                    <Text
                      numberOfLines={1}
                      style={{
                        fontSize: 13.5,
                        fontWeight: active ? '600' : '500',
                        color: active ? palette.text : palette.textSecondary,
                      }}
                    >
                      {conv.title}
                    </Text>
                  </TouchableOpacity>
                )}
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                  <TouchableOpacity
                    onPress={() => {
                      setRenamingId(conv.id);
                      setRenameText(conv.title);
                    }}
                    style={styles.convActionBtn}
                  >
                    <Ionicons name="pencil-outline" size={13} color={palette.textMuted} />
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => handleDeleteConv(conv.id)} style={styles.convActionBtn}>
                    <Ionicons name="trash-outline" size={13} color={palette.textMuted} />
                  </TouchableOpacity>
                </View>
              </View>
            );
          })
        )}

        {/* Navigation Links */}
        <Text style={[styles.sectionLabel, { color: palette.textMuted, marginTop: 16, marginBottom: 6 }]}>WORKSPACE</Text>
        {navItems
          .filter((item) => !item.adminOnly || user?.role === 'admin')
          .map((item) => {
            const active = pathname === item.path;
            return (
              <TouchableOpacity
                key={item.path}
                onPress={() => navigate(item.path)}
                style={[
                  styles.navItem,
                  { backgroundColor: active ? palette.accentSoft : 'transparent' },
                ]}
              >
                <Ionicons
                  name={item.icon}
                  size={17}
                  color={active ? palette.accent : palette.textSecondary}
                />
                <Text
                  style={{
                    fontSize: 13.5,
                    fontWeight: active ? '600' : '500',
                    color: active ? palette.accent : palette.textSecondary,
                  }}
                >
                  {item.label}
                </Text>
              </TouchableOpacity>
            );
          })}
      </ScrollView>

      {/* Footer */}
      <View style={[styles.footer, { borderTopColor: palette.border }]}>
        <View style={{ flex: 1 }}>
          <Text numberOfLines={1} style={{ fontSize: 13.5, fontWeight: '600', color: palette.text }}>
            {user?.username || 'Account'}
          </Text>
          <Text numberOfLines={1} style={{ fontSize: 11.5, color: palette.textMuted }}>
            {user?.subscription_plan?.toUpperCase()} Plan
          </Text>
        </View>
        <TouchableOpacity
          onPress={async () => {
            await logout();
            router.replace('/login' as never);
          }}
          style={[styles.iconBtn, { borderColor: palette.border }]}
        >
          <Ionicons name="log-out-outline" size={17} color={palette.danger} />
        </TouchableOpacity>
      </View>
    </View>
  );

  return (
    <View style={[styles.container, { backgroundColor: palette.bg }]}>
      {isDesktop && !sidebarCollapsed ? (
        <View style={styles.desktopSidebar}>{renderSidebarContent()}</View>
      ) : null}

      <View style={{ flex: 1, position: 'relative' }}>
        {isDesktop && sidebarCollapsed ? (
          <View style={{ position: 'absolute', top: 12, left: 12, zIndex: 20, flexDirection: 'row', gap: 6 }}>
            <TouchableOpacity
              onPress={() => setSidebarCollapsed(false)}
              style={[styles.iconBtn, { backgroundColor: palette.surface, borderColor: palette.border }]}
            >
              <Ionicons name="menu-outline" size={18} color={palette.text} />
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => navigate('/chat')}
              style={[styles.iconBtn, { backgroundColor: palette.surface, borderColor: palette.border }]}
            >
              <Ionicons name="create-outline" size={17} color={palette.accent} />
            </TouchableOpacity>
          </View>
        ) : null}
        {!isDesktop ? (
          <View style={[styles.mobileTopBar, { backgroundColor: palette.surface, borderBottomColor: palette.border }]}>
            <TouchableOpacity onPress={() => setDrawerOpen(true)} style={styles.mobileMenuBtn}>
              <Ionicons name="menu" size={22} color={palette.text} />
            </TouchableOpacity>
            <MeridianLogo size={24} />
            <TouchableOpacity onPress={() => navigate('/chat')} style={styles.mobileMenuBtn}>
              <Ionicons name="create-outline" size={20} color={palette.accent} />
            </TouchableOpacity>
          </View>
        ) : null}
        {children}
      </View>

      {/* Mobile Collapsible Drawer */}
      <Modal visible={!isDesktop && drawerOpen} transparent animationType="fade" onRequestClose={() => setDrawerOpen(false)}>
        <View style={styles.drawerOverlay}>
          <View style={[styles.drawerPanel, { backgroundColor: palette.sidebar }]}>
            {renderSidebarContent()}
          </View>
          <Pressable style={{ flex: 1 }} onPress={() => setDrawerOpen(false)} />
        </View>
      </Modal>

      {/* Create Project Modal */}
      <Modal visible={projectModalOpen} transparent animationType="fade" onRequestClose={() => setProjectModalOpen(false)}>
        <View style={styles.modalBackdrop}>
          <View style={[styles.modalCard, { backgroundColor: palette.surface, borderColor: palette.border }]}>
            <Text style={{ fontSize: 17, fontWeight: '700', color: palette.text, marginBottom: 12 }}>
              New Project Workspace
            </Text>
            <TextInput
              value={newProjName}
              onChangeText={setNewProjName}
              placeholder="Project name (e.g. Research Paper)"
              placeholderTextColor={palette.textMuted}
              style={[styles.modalInput, { color: palette.text, borderColor: palette.border, backgroundColor: palette.bg }]}
            />
            <TextInput
              value={newProjInstructions}
              onChangeText={setNewProjInstructions}
              placeholder="Custom AI instructions for this project (optional)"
              placeholderTextColor={palette.textMuted}
              multiline
              numberOfLines={3}
              style={[
                styles.modalInput,
                { color: palette.text, borderColor: palette.border, backgroundColor: palette.bg, minHeight: 80, textAlignVertical: 'top' },
              ]}
            />
            <View style={{ flexDirection: 'row', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
              <TouchableOpacity
                onPress={() => setProjectModalOpen(false)}
                style={[styles.modalBtn, { borderColor: palette.border, borderWidth: 1 }]}
              >
                <Text style={{ color: palette.textSecondary, fontWeight: '600' }}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={handleCreateProject}
                style={[styles.modalBtn, { backgroundColor: palette.accent }]}
              >
                <Text style={{ color: '#FFFFFF', fontWeight: '600' }}>Create</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, flexDirection: 'row' },
  desktopSidebar: { width: 278, height: '100%' },
  sidebarInner: {
    flex: 1,
    paddingHorizontal: 14,
    paddingTop: Platform.OS === 'web' ? 16 : 44,
    paddingBottom: 14,
    borderRightWidth: 1,
  },
  sidebarHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 14,
  },
  iconBtn: {
    width: 34,
    height: 34,
    borderRadius: 10,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  newChatBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 10,
    borderRadius: 12,
    marginBottom: 10,
  },
  newChatText: { color: '#FFFFFF', fontSize: 14, fontWeight: '600' },
  searchBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderWidth: 1,
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 7,
    marginBottom: 14,
  },
  searchInput: { flex: 1, fontSize: 13.5, padding: 0 },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 },
  sectionLabel: { fontSize: 11, fontWeight: '700', letterSpacing: 0.7 },
  projectPill: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, borderWidth: 1 },
  convRow: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: 10,
    borderWidth: 1,
    paddingHorizontal: 8,
    marginBottom: 2,
  },
  convActionBtn: { padding: 4 },
  renameInput: { flex: 1, fontSize: 13.5, borderBottomWidth: 1, paddingVertical: 4 },
  navItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: 10,
    marginBottom: 2,
  },
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingTop: 12,
    borderTopWidth: 1,
  },
  mobileTopBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 12,
    paddingTop: Platform.OS === 'web' ? 10 : 40,
    paddingBottom: 10,
    borderBottomWidth: 1,
  },
  mobileMenuBtn: { padding: 6 },
  drawerOverlay: { flex: 1, flexDirection: 'row', backgroundColor: 'rgba(0,0,0,0.45)' },
  drawerPanel: { width: 290, height: '100%' },
  modalBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  modalCard: { width: '100%', maxWidth: 420, borderRadius: 16, borderWidth: 1, padding: 20 },
  modalInput: { borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, fontSize: 14, marginBottom: 12 },
  modalBtn: { paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10 },
});

