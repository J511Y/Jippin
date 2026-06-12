import { TablePagination } from '@/components/console/table-pagination';
import { UserSearch } from '@/components/users/user-search';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from '@/components/ui/table';
import { listUsers } from '@/lib/data/users';
import {
  USER_STATUS_DOT_CLASS,
  USER_STATUS_LABELS,
  formatDateTime
} from '@/lib/labels';
import { cn } from '@/lib/utils';

export const dynamic = 'force-dynamic';

export default async function UsersPage({
  searchParams
}: {
  searchParams: Promise<{ q?: string; page?: string; size?: string }>;
}) {
  const params = await searchParams;
  const page = Math.max(1, Number(params.page) || 1);
  const { rows, total, pageSize } = await listUsers({
    q: params.q,
    page,
    size: Number(params.size)
  });
  const lastPage = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">회원</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            총 {total.toLocaleString('ko-KR')}명
          </p>
        </div>
        <UserSearch q={params.q} />
      </div>

      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>이름</TableHead>
              <TableHead>이메일</TableHead>
              <TableHead>상태</TableHead>
              <TableHead>역할</TableHead>
              <TableHead className="text-right">최근 로그인</TableHead>
              <TableHead className="text-right">가입일</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="text-muted-foreground h-24 text-center">
                  조건에 맞는 회원이 없습니다.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((user) => (
                <TableRow key={user.id}>
                  <TableCell className="font-medium">{user.display_name ?? '—'}</TableCell>
                  <TableCell className="text-muted-foreground">{user.email ?? '—'}</TableCell>
                  <TableCell>
                    {user.status ? (
                      <span className="flex items-center gap-2">
                        <span
                          className={cn(
                            'size-1.5 rounded-full',
                            USER_STATUS_DOT_CLASS[user.status] ?? 'bg-zinc-400'
                          )}
                        />
                        {USER_STATUS_LABELS[user.status] ?? user.status}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">프로필 없음</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary" className="font-normal">
                      {user.role}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground text-right text-xs tabular-nums">
                    {formatDateTime(user.last_sign_in_at)}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-right text-xs tabular-nums">
                    {formatDateTime(user.created_at)}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <TablePagination
        page={page}
        lastPage={lastPage}
        total={total}
        pageSize={pageSize}
        unitLabel="명"
      />
    </div>
  );
}
