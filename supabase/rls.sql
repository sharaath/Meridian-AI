-- Meridian AI — Supabase Row Level Security (RLS) & Private Storage Policies

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.uploaded_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.shared_conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.usage_logs ENABLE ROW LEVEL SECURITY;

-- Users: users can read and update their own profile
CREATE POLICY "users_select_own" ON public.users
    FOR SELECT USING (auth.uid() = id);
CREATE POLICY "users_update_own" ON public.users
    FOR UPDATE USING (auth.uid() = id) WITH CHECK (auth.uid() = id);

-- Projects: strict user ownership
CREATE POLICY "projects_all_own" ON public.projects
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- Conversations: strict user ownership
CREATE POLICY "conversations_all_own" ON public.conversations
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- Messages: user owns parent conversation
CREATE POLICY "messages_all_own" ON public.messages
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM public.conversations c
            WHERE c.id = messages.conversation_id AND c.user_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.conversations c
            WHERE c.id = messages.conversation_id AND c.user_id = auth.uid()
        )
    );

-- Uploaded Files: strict user ownership
CREATE POLICY "uploaded_files_all_own" ON public.uploaded_files
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- User Preferences: strict user ownership
CREATE POLICY "user_preferences_all_own" ON public.user_preferences
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- Memories: strict user ownership
CREATE POLICY "memories_all_own" ON public.memories
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- Shared Conversations: owner manages sharing
CREATE POLICY "shared_conversations_owner_all" ON public.shared_conversations
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- Usage Logs: user reads own usage
CREATE POLICY "usage_logs_select_own" ON public.usage_logs
    FOR SELECT USING (auth.uid() = user_id);

-- Private Storage Bucket for uploaded documents and images
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'meridian-uploads',
    'meridian-uploads',
    FALSE,
    20971520, -- 20MB
    ARRAY[
        'application/pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'text/plain',
        'image/png',
        'image/jpeg',
        'image/webp',
        'image/gif',
        'audio/webm',
        'audio/mp4',
        'audio/wav',
        'audio/mpeg'
    ]
)
ON CONFLICT (id) DO NOTHING;

-- Storage RLS: users can only access objects under <user_id>/...
CREATE POLICY "storage_own_folder_select" ON storage.objects
    FOR SELECT USING (
        bucket_id = 'meridian-uploads'
        AND auth.uid()::text = (storage.foldername(name))[1]
    );

CREATE POLICY "storage_own_folder_insert" ON storage.objects
    FOR INSERT WITH CHECK (
        bucket_id = 'meridian-uploads'
        AND auth.uid()::text = (storage.foldername(name))[1]
    );

CREATE POLICY "storage_own_folder_delete" ON storage.objects
    FOR DELETE USING (
        bucket_id = 'meridian-uploads'
        AND auth.uid()::text = (storage.foldername(name))[1]
    );

