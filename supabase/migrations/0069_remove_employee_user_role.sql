-- 0069_remove_employee_user_role.sql
-- Removes the assignable "Employee/User" company role:
--   1) Purge it from every org: role rows, user assignments, dashboard access.
--   2) Remove the now unreachable "Employee Dashboard" seeded for it.
--   3) Re-define the org seeding functions WITHOUT the role so future orgs
--      never get it back.
-- Legacy migration-0059 "Employee" rows are intentionally NOT touched: they
-- belong to the old 3-role seed and keep their personal dashboard access.
-- (The product now has 1 platform role + 10 company roles.)

-- =====================================================================
-- 1) PURGE existing rows
-- =====================================================================

-- Dashboard access rows granted to the role.
DELETE FROM public.dashboard_role_access
WHERE role_name = 'Employee/User';

-- Member assignments (user_roles FK cascade would not fire for roles today,
-- so unlink explicitly before dropping the role rows).
DELETE FROM public.user_roles ur
USING public.roles r
WHERE r.id = ur.role_id
  AND r.name = 'Employee/User';

DELETE FROM public.roles
WHERE name = 'Employee/User';

-- The default Employee Dashboard is unreachable without the role; drop it
-- (dashboard_role_access rows cascade with the dashboard).
DELETE FROM public.dashboards
WHERE name = 'Employee Dashboard';

-- =====================================================================
-- 2) RE-SEED future orgs without the role
-- =====================================================================

CREATE OR REPLACE FUNCTION public.seed_default_roles(p_org_id UUID)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    INSERT INTO public.roles (organization_id, name, description, permissions)
    VALUES
        (p_org_id, 'Company Admin',
         'Full control over the company workspace, members, billing, and AI workforce.',
         '{"manage_org":true,"manage_members":true,"manage_billing":true,"manage_ai":true,"manage_workflows":true,"use_tools":true}'::jsonb),
        (p_org_id, 'CEO / Executive',
         'Oversee the whole company, view reports and analytics.',
         '{"manage_org":true,"view_all":true,"manage_ai":true,"manage_workflows":true,"use_tools":true}'::jsonb),
        (p_org_id, 'Sales Manager',
         'Manage the sales team, CRM, leads, and quotations.',
         '{"manage_sales":true,"manage_crm":true,"manage_quotations":true,"use_tools":true}'::jsonb),
        (p_org_id, 'Sales Executive',
         'Work leads, deals, and quotations assigned to them.',
         '{"manage_crm":true,"manage_quotations":true,"use_tools":true}'::jsonb),
        (p_org_id, 'HR Manager',
         'Manage employees, hiring, and HR workflows.',
         '{"manage_hr":true,"manage_employees":true,"use_tools":true}'::jsonb),
        (p_org_id, 'Finance Manager',
         'Manage budgets, expenses, and financial reports.',
         '{"manage_finance":true,"manage_budgets":true,"use_tools":true}'::jsonb),
        (p_org_id, 'Accountant',
         'Create invoices, record payments, and manage accounting.',
         '{"manage_invoices":true,"manage_payments":true,"use_tools":true}'::jsonb),
        (p_org_id, 'Customer Support',
         'Respond to customers via email and WhatsApp.',
         '{"manage_support":true,"use_tools":true}'::jsonb),
        (p_org_id, 'Marketing Manager',
         'Manage marketing campaigns and content.',
         '{"manage_marketing":true,"use_tools":true}'::jsonb),
        (p_org_id, 'Operations Manager',
         'Manage tasks, workflows, and daily operations.',
         '{"manage_operations":true,"manage_tasks":true,"manage_workflows":true,"use_tools":true}'::jsonb)
    ON CONFLICT (organization_id, name) DO NOTHING;
END;
$$;

CREATE OR REPLACE FUNCTION public.seed_default_dashboards(p_org_id UUID)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    PERFORM public._seed_dashboard(p_org_id, 'Super Admin Dashboard',
        'Platform-wide administration and company oversight.', ARRAY['Super Admin']);
    PERFORM public._seed_dashboard(p_org_id, 'Company Admin Dashboard',
        'Company-wide overview and member management.', ARRAY['Company Admin']);
    PERFORM public._seed_dashboard(p_org_id, 'CEO / Executive Dashboard',
        'Executive KPIs, revenue, and high-level analytics.', ARRAY['CEO / Executive']);
    PERFORM public._seed_dashboard(p_org_id, 'Sales Dashboard',
        'Sales pipeline, leads, and quotation performance.', ARRAY['Sales Manager', 'Sales Executive']);
    PERFORM public._seed_dashboard(p_org_id, 'CRM Dashboard',
        'Customers, leads, and relationship insights.', ARRAY['Company Admin', 'Sales Manager', 'Sales Executive']);
    PERFORM public._seed_dashboard(p_org_id, 'HR Dashboard',
        'Employees, attendance, and hiring overview.', ARRAY['HR Manager']);
    PERFORM public._seed_dashboard(p_org_id, 'Finance Dashboard',
        'Revenue, expenses, budgets, and cash flow.', ARRAY['Finance Manager', 'Accountant']);
    PERFORM public._seed_dashboard(p_org_id, 'Customer Support Dashboard',
        'Support tickets, email, and WhatsApp activity.', ARRAY['Customer Support']);
    PERFORM public._seed_dashboard(p_org_id, 'Marketing Dashboard',
        'Campaigns, content, and audience performance.', ARRAY['Marketing Manager']);
    PERFORM public._seed_dashboard(p_org_id, 'Operations Dashboard',
        'Tasks, workflows, and operational efficiency.', ARRAY['Operations Manager']);
    PERFORM public._seed_dashboard(p_org_id, 'AI Employees Dashboard',
        'Manage the AI workforce, tools, and usage.', ARRAY['Company Admin', 'CEO / Executive']);
    PERFORM public._seed_dashboard(p_org_id, 'Reports & Analytics Dashboard',
        'Reports and analytics for managers and above.', ARRAY['Company Admin', 'CEO / Executive',
            'Sales Manager', 'HR Manager', 'Finance Manager', 'Marketing Manager', 'Operations Manager']);
    PERFORM public._seed_dashboard(p_org_id, 'Settings & Integrations Dashboard',
        'Company settings and connected applications.', ARRAY['Company Admin', 'CEO / Executive']);
END;
$$;
