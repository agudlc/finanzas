import { Outlet } from '@tanstack/react-router';

export default function BaseLayout() {
    return (
        <>
            <div className="h-full w-full overflow-x-hidden overflow-y-auto p-5 flex flex-col items-center justify-center gap-5">
                <Outlet />
            </div>
        </>
    )
}