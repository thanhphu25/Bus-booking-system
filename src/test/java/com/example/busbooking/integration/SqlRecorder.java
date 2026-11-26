package com.example.busbooking.integration;

import org.hibernate.resource.jdbc.spi.StatementInspector;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

/** Test-only Hibernate StatementInspector that records every SQL statement prepared by Hibernate. */
public class SqlRecorder implements StatementInspector {
    private static final List<String> STATEMENTS = new CopyOnWriteArrayList<>();

    @Override
    public String inspect(String sql) {
        STATEMENTS.add(sql);
        return sql;
    }

    static void clear() {
        STATEMENTS.clear();
    }

    static List<String> statements() {
        return new ArrayList<>(STATEMENTS);
    }
}
